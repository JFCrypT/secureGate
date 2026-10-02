"""Heartbeat del runtime para que el frontend no invente estado de hardware."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from securegate.rfid.registry import DEFAULT_DB


SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_status (
    runtime_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    methods TEXT NOT NULL,
    door_mode TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class RuntimeStatusRepository:
    def __init__(self, database=DEFAULT_DB, clock=None):
        self.database = Path(database)
        if not self.database.is_file():
            raise ValueError("Base inexistente. Ejecutar raspberry/init_db.py primero.")
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout = 5000")
            with connection:
                yield connection
        finally:
            connection.close()

    def update(self, status, methods, door_mode, runtime_name="access"):
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("El heartbeat debe usar fecha con zona horaria.")
        updated_at = now.astimezone(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO runtime_status (
                       runtime_name, status, methods, door_mode, updated_at
                   ) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(runtime_name) DO UPDATE SET
                       status = excluded.status,
                       methods = excluded.methods,
                       door_mode = excluded.door_mode,
                       updated_at = excluded.updated_at""",
                (runtime_name, status, methods, door_mode, updated_at),
            )

    def get(self, runtime_name="access", online_seconds=15):
        now = self.clock().astimezone(timezone.utc)
        with self._connect() as connection:
            row = connection.execute(
                """SELECT status, methods, door_mode, updated_at
                   FROM runtime_status WHERE runtime_name = ?""",
                (runtime_name,),
            ).fetchone()
        if row is None:
            return {
                "online": False,
                "status": "unknown",
                "methods": None,
                "door_mode": None,
                "updated_at": None,
            }
        updated_at = datetime.fromisoformat(row["updated_at"])
        age = (now - updated_at).total_seconds()
        return {
            "online": row["status"] == "running" and 0 <= age <= online_seconds,
            "status": row["status"],
            "methods": row["methods"],
            "door_mode": row["door_mode"],
            "updated_at": row["updated_at"],
        }
