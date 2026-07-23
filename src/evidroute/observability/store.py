from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from evidroute.models import QueryTrace


class TraceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    query TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    correct INTEGER,
                    supported INTEGER,
                    comment TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save(self, trace: QueryTrace) -> None:
        payload = trace.canonical_json()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO traces(trace_id, created_at, query, payload) VALUES (?, ?, ?, ?)",
                (trace.trace_id, trace.created_at.isoformat(), trace.query, payload),
            )

    def get(self, trace_id: str) -> QueryTrace | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM traces WHERE trace_id = ?", (trace_id,)
            ).fetchone()
        if row is None:
            return None
        return QueryTrace.model_validate(json.loads(row[0]))

    def add_feedback(
        self,
        trace_id: str,
        correct: bool | None,
        supported: bool | None,
        comment: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO feedback(trace_id, correct, supported, comment) VALUES (?, ?, ?, ?)",
                (
                    trace_id,
                    None if correct is None else int(correct),
                    None if supported is None else int(supported),
                    comment,
                ),
            )
