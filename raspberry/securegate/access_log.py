"""Registro persistente de decisiones de acceso en SQLite."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from securegate.rfid.registry import DEFAULT_DB


SCHEMA = """
CREATE TABLE IF NOT EXISTS access_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    method TEXT NOT NULL,
    external_id TEXT,
    granted INTEGER NOT NULL CHECK (granted IN (0, 1)),
    restricted_time INTEGER NOT NULL CHECK (restricted_time IN (0, 1)),
    alert_reasons TEXT NOT NULL DEFAULT '',
    door_status TEXT NOT NULL
        CHECK (door_status IN ('opened', 'simulated', 'not_requested', 'error')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_access_events_occurred_at
ON access_events(occurred_at);

CREATE INDEX IF NOT EXISTS idx_access_events_external_id
ON access_events(external_id);
"""


class AccessLogRepository:
    def __init__(self, database=DEFAULT_DB):
        self.database = Path(database)
        if not self.database.is_file():
            raise ValueError("Base inexistente. Ejecutar raspberry/init_db.py primero.")
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

    def record(
        self,
        event,
        restricted_time,
        alert_reasons=(),
        door_status="not_requested",
    ):
        moment = event.occurred_at
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("El evento debe tener fecha y hora con zona horaria.")
        reasons = " | ".join(str(reason) for reason in alert_reasons)
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO access_events (
                       occurred_at, method, external_id, granted,
                       restricted_time, alert_reasons, door_status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    moment.isoformat(timespec="seconds"),
                    event.method,
                    event.user,
                    int(event.granted),
                    int(bool(restricted_time)),
                    reasons,
                    door_status,
                ),
            )
            return cursor.lastrowid

    def list(self, limit=50, offset=0, date_prefix=None, method=None, granted=None):
        if not 1 <= limit <= 500:
            raise ValueError("limit debe estar entre 1 y 500.")
        if offset < 0:
            raise ValueError("offset no puede ser negativo.")
        conditions = []
        parameters = []
        if date_prefix:
            conditions.append("occurred_at LIKE ?")
            parameters.append(f"{date_prefix}%")
        if method:
            conditions.append("method = ?")
            parameters.append(method)
        if granted is not None:
            conditions.append("granted = ?")
            parameters.append(int(bool(granted)))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.extend((limit, offset))
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT event_id, occurred_at, method, external_id, granted,
                           restricted_time, alert_reasons, door_status
                    FROM access_events
                    {where}
                    ORDER BY event_id DESC
                    LIMIT ? OFFSET ?""",
                parameters,
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "occurred_at": row["occurred_at"],
                "method": row["method"],
                "external_id": row["external_id"],
                "granted": bool(row["granted"]),
                "restricted_time": bool(row["restricted_time"]),
                "alert_reasons": [
                    reason for reason in row["alert_reasons"].split(" | ") if reason
                ],
                "door_status": row["door_status"],
            }
            for row in rows
        ]

    def summary(self, date_prefix=None):
        where = "WHERE occurred_at LIKE ?" if date_prefix else ""
        parameters = (f"{date_prefix}%",) if date_prefix else ()
        with self._connect() as connection:
            row = connection.execute(
                f"""SELECT COUNT(*) AS total,
                           COALESCE(SUM(granted), 0) AS granted,
                           COALESCE(SUM(CASE WHEN granted = 0 THEN 1 ELSE 0 END), 0)
                               AS denied,
                           COALESCE(SUM(restricted_time), 0) AS restricted,
                           COALESCE(SUM(CASE WHEN door_status = 'error' THEN 1 ELSE 0 END), 0)
                               AS door_errors
                    FROM access_events {where}""",
                parameters,
            ).fetchone()
        return {name: int(row[name]) for name in row.keys()}
