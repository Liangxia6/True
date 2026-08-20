"""Repeatable forward SQLite migrations with a pre-migration backup."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.core.timeutil import to_iso

MIGRATIONS = ("v001_initial.sql",)


def _load_sql(name: str) -> str:
    return resources.files("trueeval.storage.migrations").joinpath(name).read_text(encoding="utf-8")


def backup_db(db_path: Path) -> Path | None:
    if not db_path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = db_path.with_name(f"{db_path.name}.bak.{stamp}")
    shutil.copy2(db_path, dest)
    return dest


def apply_migrations(conn: sqlite3.Connection, db_path: Path | None = None) -> list[str]:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    newly: list[str] = []
    for name in MIGRATIONS:
        version = name.removesuffix(".sql")
        if version in applied:
            continue
        if db_path is not None:
            backup_db(db_path)
        try:
            conn.executescript(_load_sql(name))
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, to_iso(datetime.now(timezone.utc))),
            )
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise TrueEvalError(
                f"migration {version} failed",
                category=FailureCategory.STORAGE_ERROR,
                code="migration_failed",
                retryable=False,
                cause=exc,
            ) from exc
        newly.append(version)
    return newly
