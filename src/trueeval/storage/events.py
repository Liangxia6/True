"""Project transactional outbox events to append-only JSONL."""

from __future__ import annotations

from pathlib import Path

from trueeval.core.hashing import canonical_json
from trueeval.core.schemas.common import dump_canonical
from trueeval.storage.artifacts import ArtifactStore
from trueeval.storage.state import StateStore


class EventProjector:
    """JSONL is a projection. SQLite outbox remains the source of truth."""

    def __init__(self, store: StateStore, artifacts: ArtifactStore) -> None:
        self.store = store
        self.artifacts = artifacts

    def events_path(self, run_id: str) -> Path:
        return self.artifacts.run_path(run_id) / "events.jsonl"

    def last_file_seq(self, run_id: str) -> int:
        path = self.events_path(run_id)
        if not path.exists():
            return 0
        last = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            import json

            last = max(last, int(json.loads(line)["event_sequence"]))
        return last

    def project(self, run_id: str) -> int:
        after = max(self.store.last_projected_seq(run_id), self.last_file_seq(run_id))
        events = self.store.unprojected_events(run_id, after_seq=after)
        if not events:
            return after
        path = self.events_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            for event in events:
                handle.write(canonical_json(dump_canonical(event)) + "\n")
            handle.flush()
        self.store.mark_projected(run_id, events[-1].event_sequence)
        return events[-1].event_sequence

    def rebuild(self, run_id: str) -> int:
        """Rebuild JSONL from outbox. Existing file is replaced atomically."""
        events = self.store.unprojected_events(run_id, after_seq=0)
        rows = [dump_canonical(event) for event in events]
        relative = f"runs/{run_id}/events.jsonl"
        self.artifacts.write_jsonl(relative, rows, overwrite=True)
        if events:
            self.store.mark_projected(run_id, events[-1].event_sequence)
            return events[-1].event_sequence
        return 0
