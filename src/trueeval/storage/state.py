"""SQLite State Store. Status changes and outbox events share one transaction."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from trueeval.core.errors import ErrorInfo, FailureCategory, TrueEvalError
from trueeval.core.hashing import canonical_json
from trueeval.core.ids import uuid7
from trueeval.core.schemas.events import EventRecord
from trueeval.core.schemas.score import GradingJob, ScoreRecord
from trueeval.core.schemas.sut import Submission
from trueeval.core.schemas.task import TaskRun
from trueeval.core.state_machine.states import TERMINAL_STATES, TaskRunState
from trueeval.core.state_machine.transitions import StateTransitionService
from trueeval.core.timeutil import Clock, SystemClock, to_iso, utc_now
from trueeval.storage.migrate import apply_migrations


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    apply_migrations(conn, db_path)
    return conn


class StateStore:
    def __init__(self, db_path: Path, *, clock: Clock | None = None) -> None:
        self.db_path = Path(db_path)
        self.clock = clock or SystemClock()
        self.conn = connect(self.db_path)
        self.transitions = StateTransitionService(now=self.clock.now)

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def txn(self) -> Iterator[sqlite3.Connection]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def create_run(
        self,
        *,
        run_id: str,
        manifest_uri: str,
        manifest_hash: str,
        created_by: str,
    ) -> None:
        now = to_iso(self.clock.now())
        with self.txn():
            self.conn.execute(
                """
                INSERT INTO runs(run_id, status, manifest_uri, manifest_hash, created_at, updated_at, created_by)
                VALUES (?, 'created', ?, ?, ?, ?, ?)
                """,
                (run_id, manifest_uri, manifest_hash, now, now, created_by),
            )
            self._outbox(run_id, run_id, "run.created", {"manifest_uri": manifest_uri})

    def set_run_status(self, run_id: str, status: str, payload: dict[str, Any] | None = None) -> None:
        now = to_iso(self.clock.now())
        with self.txn():
            self.conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (status, now, run_id),
            )
            self._outbox(run_id, run_id, f"run.{status}", payload or {})

    def get_run(self, run_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()

    def insert_task_run(self, task: TaskRun) -> None:
        with self.txn():
            self._insert_task_run(task)
            self._outbox(
                task.run_id,
                task.execution_id,
                "task.created",
                {"task_id": task.task_id, "repeat_index": task.repeat_index},
            )

    def insert_task_runs(self, tasks: list[TaskRun]) -> None:
        with self.txn():
            for task in tasks:
                self._insert_task_run(task)
                self._outbox(
                    task.run_id,
                    task.execution_id,
                    "task.created",
                    {"task_id": task.task_id, "repeat_index": task.repeat_index},
                )

    def _insert_task_run(self, task: TaskRun) -> None:
        self.conn.execute(
            """
            INSERT INTO task_runs(
                execution_id, run_id, task_id, repeat_index, status, attempt_count,
                idempotency_key, external_job_id, deadline, last_error_json,
                input_uri, output_uri, raw_result_uri, answer_uri, session_id,
                created_at, submitted_at, completed_at, updated_at, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.execution_id,
                task.run_id,
                task.task_id,
                task.repeat_index,
                task.status.value,
                task.attempt_count,
                task.idempotency_key,
                task.external_job_id,
                to_iso(task.deadline) if task.deadline else None,
                task.last_error.model_dump_json() if task.last_error else None,
                task.input_uri,
                task.output_uri,
                task.raw_result_uri,
                task.answer_uri,
                task.session_id,
                to_iso(task.created_at),
                to_iso(task.submitted_at) if task.submitted_at else None,
                to_iso(task.completed_at) if task.completed_at else None,
                to_iso(task.updated_at),
                canonical_json(task.extra),
            ),
        )

    def get_task_run(self, execution_id: str) -> TaskRun | None:
        row = self.conn.execute(
            "SELECT * FROM task_runs WHERE execution_id = ?", (execution_id,)
        ).fetchone()
        return self._task_from_row(row) if row else None

    def list_task_runs(self, run_id: str) -> list[TaskRun]:
        rows = self.conn.execute(
            "SELECT * FROM task_runs WHERE run_id = ? ORDER BY task_id, repeat_index",
            (run_id,),
        ).fetchall()
        return [self._task_from_row(r) for r in rows]

    def list_nonterminal(self, run_id: str | None = None) -> list[TaskRun]:
        terminal = tuple(s.value for s in TERMINAL_STATES)
        placeholders = ",".join("?" * len(terminal))
        sql = f"SELECT * FROM task_runs WHERE status NOT IN ({placeholders})"
        params: list[Any] = list(terminal)
        if run_id:
            sql += " AND run_id = ?"
            params.append(run_id)
        sql += " ORDER BY created_at"
        return [self._task_from_row(r) for r in self.conn.execute(sql, params).fetchall()]

    def transition(
        self,
        execution_id: str,
        target: TaskRunState,
        *,
        event_type: str,
        payload: dict[str, Any] | None = None,
        error: ErrorInfo | None = None,
        updates: dict[str, Any] | None = None,
    ) -> TaskRun:
        """Update TaskRun status and write an outbox event in one transaction."""
        with self.txn():
            row = self.conn.execute(
                "SELECT * FROM task_runs WHERE execution_id = ?", (execution_id,)
            ).fetchone()
            if row is None:
                raise TrueEvalError(
                    f"unknown execution {execution_id}",
                    category=FailureCategory.STATE_ERROR,
                    code="missing_task_run",
                    retryable=False,
                )
            current = TaskRunState(row["status"])
            new_state, when = self.transitions.apply(current=current, target=target, error=error)
            fields = {
                "status": new_state.value,
                "updated_at": to_iso(when),
            }
            if error is not None:
                fields["last_error_json"] = error.model_dump_json()
            if new_state in {
                TaskRunState.SCORED,
                TaskRunState.FAILED_FINAL,
                TaskRunState.TIMED_OUT,
                TaskRunState.CANCELLED,
                TaskRunState.UNSUPPORTED,
            }:
                fields["completed_at"] = to_iso(when)
            if updates:
                fields.update(updates)
            assignments = ", ".join(f"{k} = ?" for k in fields)
            self.conn.execute(
                f"UPDATE task_runs SET {assignments} WHERE execution_id = ?",
                [*fields.values(), execution_id],
            )
            event_payload = {"from": current.value, "to": new_state.value, **(payload or {})}
            if error:
                event_payload["error_category"] = error.category.value
                event_payload["error_code"] = error.code
            self._outbox(row["run_id"], execution_id, event_type, event_payload)
        loaded = self.get_task_run(execution_id)
        assert loaded is not None
        return loaded

    def patch_task(self, execution_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = to_iso(self.clock.now())
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self.txn():
            self.conn.execute(
                f"UPDATE task_runs SET {assignments} WHERE execution_id = ?",
                [*fields.values(), execution_id],
            )

    def add_submission(self, submission: Submission) -> None:
        with self.txn():
            self.conn.execute(
                """
                INSERT INTO submissions(
                    submission_id, execution_id, idempotency_key, external_job_id,
                    channel, submitted_at, request_uri, response_uri, lookup_available
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission.submission_id,
                    submission.execution_id,
                    submission.idempotency_key,
                    submission.external_job_id,
                    submission.channel,
                    to_iso(submission.submitted_at),
                    submission.request_uri,
                    submission.response_uri,
                    int(submission.lookup_available),
                ),
            )
            self._outbox(
                self._run_id_for(submission.execution_id),
                submission.execution_id,
                "sut.submitted",
                {
                    "external_job_id": submission.external_job_id,
                    "idempotency_key": submission.idempotency_key,
                },
            )

    def add_attempt(self, execution_id: str, attempt_index: int) -> str:
        attempt_id = uuid7()
        with self.txn():
            self.conn.execute(
                "INSERT INTO attempts(attempt_id, execution_id, attempt_index, created_at) VALUES (?, ?, ?, ?)",
                (attempt_id, execution_id, attempt_index, to_iso(self.clock.now())),
            )
        return attempt_id

    def add_grading_job(self, job: GradingJob) -> None:
        with self.txn():
            self.conn.execute(
                """
                INSERT INTO grading_jobs(
                    grading_job_id, run_id, execution_id, grader_id, grader_version,
                    status, config_hash, selected, created_at, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.grading_job_id,
                    job.run_id,
                    job.execution_id,
                    job.grader_id,
                    job.grader_version,
                    job.status,
                    job.config_hash,
                    int(job.selected),
                    to_iso(job.created_at),
                    canonical_json(job.extra),
                ),
            )
            self._outbox(job.run_id, job.grading_job_id, "grader.started", {"grader_id": job.grader_id})

    def set_grading_job_status(self, grading_job_id: str, status: str, *, selected: bool | None = None) -> None:
        with self.txn():
            if selected is None:
                self.conn.execute(
                    "UPDATE grading_jobs SET status = ? WHERE grading_job_id = ?",
                    (status, grading_job_id),
                )
            else:
                self.conn.execute(
                    "UPDATE grading_jobs SET status = ?, selected = ? WHERE grading_job_id = ?",
                    (status, int(selected), grading_job_id),
                )
            run_id = self.conn.execute(
                "SELECT run_id FROM grading_jobs WHERE grading_job_id = ?",
                (grading_job_id,),
            ).fetchone()[0]
            self._outbox(run_id, grading_job_id, f"grader.{status}", {})

    def select_grading_job(self, run_id: str, grader_id: str, grading_job_id: str) -> None:
        with self.txn():
            self.conn.execute(
                "UPDATE grading_jobs SET selected = 0 WHERE run_id = ? AND grader_id = ?",
                (run_id, grader_id),
            )
            self.conn.execute(
                "UPDATE grading_jobs SET selected = 1 WHERE grading_job_id = ?",
                (grading_job_id,),
            )
            self._outbox(run_id, grading_job_id, "grader.selected", {"grader_id": grader_id})

    def add_scores(self, scores: list[ScoreRecord]) -> None:
        if not scores:
            return
        with self.txn():
            for score in scores:
                self.conn.execute(
                    """
                    INSERT INTO score_records(
                        score_id, run_id, execution_id, grading_job_id, task_id,
                        repeat_index, grader_id, metric, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        score.score_id,
                        score.run_id,
                        score.execution_id,
                        score.grading_job_id,
                        score.task_id,
                        score.repeat_index,
                        score.grader_id,
                        score.metric,
                        score.model_dump_json(),
                        to_iso(score.created_at),
                    ),
                )

    def list_scores(self, run_id: str, *, selected_only: bool = False) -> list[ScoreRecord]:
        if selected_only:
            rows = self.conn.execute(
                """
                SELECT s.payload_json FROM score_records s
                JOIN grading_jobs g ON g.grading_job_id = s.grading_job_id
                WHERE s.run_id = ? AND g.selected = 1
                ORDER BY s.task_id, s.repeat_index, s.metric
                """,
                (run_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT payload_json FROM score_records WHERE run_id = ? ORDER BY task_id, repeat_index, metric",
                (run_id,),
            ).fetchall()
        return [ScoreRecord.model_validate_json(r[0]) for r in rows]

    def reserve_budget(self, run_id: str, execution_id: str, amount: float, cap: float) -> str:
        reservation_id = uuid7()
        now = to_iso(self.clock.now())
        with self.txn():
            used = self.conn.execute(
                """
                SELECT COALESCE(SUM(CASE WHEN released = 0 THEN reserved_usd ELSE COALESCE(actual_usd, reserved_usd) END), 0)
                FROM budget_ledger WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()[0]
            if used + amount > cap + 1e-9:
                raise TrueEvalError(
                    "run budget hard limit would be exceeded",
                    category=FailureCategory.BUDGET_EXCEEDED,
                    code="budget_exceeded",
                    retryable=False,
                    details={"used": used, "reserve": amount, "cap": cap},
                )
            self.conn.execute(
                """
                INSERT INTO budget_ledger(reservation_id, run_id, execution_id, reserved_usd, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (reservation_id, run_id, execution_id, amount, now),
            )
            self._outbox(
                run_id,
                execution_id,
                "budget.reserved",
                {"reservation_id": reservation_id, "reserved_usd": amount, "used": used + amount},
            )
        return reservation_id

    def settle_budget(self, reservation_id: str, actual: float | None) -> None:
        now = to_iso(self.clock.now())
        with self.txn():
            row = self.conn.execute(
                "SELECT run_id, execution_id FROM budget_ledger WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if row is None:
                return
            self.conn.execute(
                """
                UPDATE budget_ledger SET actual_usd = ?, released = 1, settled_at = ?
                WHERE reservation_id = ?
                """,
                (actual, now, reservation_id),
            )
            self._outbox(
                row["run_id"],
                row["execution_id"],
                "budget.settled",
                {"reservation_id": reservation_id, "actual_usd": actual},
            )

    def budget_used(self, run_id: str) -> float:
        value = self.conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN released = 0 THEN reserved_usd ELSE COALESCE(actual_usd, reserved_usd) END), 0)
            FROM budget_ledger WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]
        return float(value)

    def unprojected_events(self, run_id: str, after_seq: int = 0) -> list[EventRecord]:
        rows = self.conn.execute(
            """
            SELECT * FROM outbox_events
            WHERE run_id = ? AND event_sequence > ?
            ORDER BY event_sequence
            """,
            (run_id, after_seq),
        ).fetchall()
        return [self._event_from_row(r) for r in rows]

    def mark_projected(self, run_id: str, up_to: int) -> None:
        with self.txn():
            self.conn.execute(
                "UPDATE outbox_events SET projected = 1 WHERE run_id = ? AND event_sequence <= ?",
                (run_id, up_to),
            )

    def last_projected_seq(self, run_id: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(event_sequence), 0) FROM outbox_events WHERE run_id = ? AND projected = 1",
            (run_id,),
        ).fetchone()
        return int(row[0])

    def _outbox(self, run_id: str, entity_id: str, event_type: str, payload: dict[str, Any]) -> None:
        seq_row = self.conn.execute(
            "SELECT COALESCE(MAX(event_sequence), 0) FROM outbox_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        seq = int(seq_row[0]) + 1
        self.conn.execute(
            """
            INSERT INTO outbox_events(run_id, event_sequence, event_type, entity_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, seq, event_type, entity_id, canonical_json(payload), to_iso(self.clock.now())),
        )

    def _run_id_for(self, execution_id: str) -> str:
        row = self.conn.execute(
            "SELECT run_id FROM task_runs WHERE execution_id = ?", (execution_id,)
        ).fetchone()
        if row is None:
            raise TrueEvalError(
                "execution missing while writing event",
                category=FailureCategory.STATE_ERROR,
                code="missing_task_run",
                retryable=False,
            )
        return str(row[0])

    def _task_from_row(self, row: sqlite3.Row) -> TaskRun:
        error = ErrorInfo.model_validate_json(row["last_error_json"]) if row["last_error_json"] else None
        extra = json.loads(row["extra_json"] or "{}")
        return TaskRun(
            run_id=row["run_id"],
            execution_id=row["execution_id"],
            task_id=row["task_id"],
            repeat_index=row["repeat_index"],
            status=TaskRunState(row["status"]),
            attempt_count=row["attempt_count"],
            idempotency_key=row["idempotency_key"],
            external_job_id=row["external_job_id"],
            deadline=datetime.fromisoformat(row["deadline"].replace("Z", "+00:00")) if row["deadline"] else None,
            last_error=error,
            input_uri=row["input_uri"],
            output_uri=row["output_uri"],
            raw_result_uri=row["raw_result_uri"],
            answer_uri=row["answer_uri"],
            session_id=row["session_id"],
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
            submitted_at=datetime.fromisoformat(row["submitted_at"].replace("Z", "+00:00"))
            if row["submitted_at"]
            else None,
            completed_at=datetime.fromisoformat(row["completed_at"].replace("Z", "+00:00"))
            if row["completed_at"]
            else None,
            updated_at=datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")),
            extra=extra,
        )

    def _event_from_row(self, row: sqlite3.Row) -> EventRecord:
        return EventRecord(
            run_id=row["run_id"],
            event_sequence=row["event_sequence"],
            event_type=row["event_type"],
            entity_id=row["entity_id"],
            payload=json.loads(row["payload_json"]),
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
        )


def now_iso() -> str:
    return to_iso(utc_now())
