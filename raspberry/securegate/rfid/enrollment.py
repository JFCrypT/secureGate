"""Cola SQLite para enrolar RFID sin entregar el lector ni el UID a la API."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from securegate.rfid.registry import DEFAULT_DB
from securegate.users import UserNotFound, validate_external_id


SCHEMA = """
CREATE TABLE IF NOT EXISTS rfid_enrollment_requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'completed', 'cancelled', 'failed', 'expired')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    finished_at TEXT,
    error_code TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rfid_enrollment_one_pending
ON rfid_enrollment_requests(status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_rfid_enrollment_user
ON rfid_enrollment_requests(user_id);
"""


class EnrollmentBusy(ValueError):
    pass


class EnrollmentNotFound(ValueError):
    pass


class EnrollmentConflict(ValueError):
    pass


class RFIDEnrollmentRepository:
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
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            with connection:
                yield connection
        finally:
            connection.close()

    def _now(self):
        moment = self.clock()
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("El reloj de enrolamiento debe incluir zona horaria.")
        return moment.astimezone(timezone.utc)

    @staticmethod
    def _serialize(row):
        return {
            "request_id": row["request_id"],
            "external_id": row["external_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "finished_at": row["finished_at"],
            "error_code": row["error_code"],
        }

    @staticmethod
    def _select(connection, clause, parameters):
        return connection.execute(
            f"""SELECT r.request_id, u.external_id, r.status, r.created_at,
                       r.expires_at, r.finished_at, r.error_code
                FROM rfid_enrollment_requests r
                JOIN users u ON u.user_id = r.user_id
                WHERE {clause}""",
            parameters,
        ).fetchone()

    def _expire(self, connection, now):
        now_text = now.isoformat(timespec="seconds")
        connection.execute(
            """UPDATE rfid_enrollment_requests
               SET status = 'expired', finished_at = ?
               WHERE status = 'pending' AND expires_at <= ?""",
            (now_text, now_text),
        )

    def create(self, external_id, timeout_seconds=60):
        validate_external_id(external_id)
        if not 10 <= timeout_seconds <= 300:
            raise ValueError("El tiempo de enrolamiento debe estar entre 10 y 300 s.")
        now = self._now()
        expires = now + timedelta(seconds=timeout_seconds)
        with self._connect() as connection:
            self._expire(connection, now)
            user = connection.execute(
                "SELECT user_id, active FROM users WHERE external_id = ?",
                (external_id,),
            ).fetchone()
            if user is None:
                raise UserNotFound("Usuario inexistente.")
            if not user["active"]:
                raise EnrollmentConflict("El usuario está deshabilitado.")
            has_rfid_table = connection.execute(
                """SELECT 1 FROM sqlite_master
                   WHERE type = 'table' AND name = 'rfid_credentials'"""
            ).fetchone()
            if has_rfid_table and connection.execute(
                """SELECT 1 FROM rfid_credentials
                   WHERE user_id = ? AND active = 1""",
                (user["user_id"],),
            ).fetchone():
                raise EnrollmentConflict(
                    "El usuario ya posee una tarjeta activa; revocarla primero."
                )
            try:
                cursor = connection.execute(
                    """INSERT INTO rfid_enrollment_requests (
                           user_id, status, created_at, expires_at
                       ) VALUES (?, 'pending', ?, ?)""",
                    (
                        user["user_id"],
                        now.isoformat(timespec="seconds"),
                        expires.isoformat(timespec="seconds"),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise EnrollmentBusy(
                    "Ya existe otra solicitud de enrolamiento pendiente."
                ) from exc
            row = self._select(connection, "r.request_id = ?", (cursor.lastrowid,))
        return self._serialize(row)

    def get(self, request_id):
        now = self._now()
        with self._connect() as connection:
            self._expire(connection, now)
            row = self._select(connection, "r.request_id = ?", (request_id,))
            if row is None:
                raise EnrollmentNotFound("Solicitud inexistente.")
        return self._serialize(row)

    def pending(self):
        now = self._now()
        with self._connect() as connection:
            self._expire(connection, now)
            row = self._select(connection, "r.status = 'pending'", ())
        return self._serialize(row) if row else None

    def _finish(self, request_id, status, error_code=None):
        now_text = self._now().isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE rfid_enrollment_requests
                   SET status = ?, finished_at = ?, error_code = ?
                   WHERE request_id = ? AND status = 'pending'""",
                (status, now_text, error_code, request_id),
            )
            if cursor.rowcount == 0:
                raise EnrollmentNotFound("La solicitud no está pendiente.")
        return self.get(request_id)

    def complete(self, request_id):
        return self._finish(request_id, "completed")

    def fail(self, request_id, error_code="card_unavailable"):
        return self._finish(request_id, "failed", error_code)

    def cancel(self, request_id):
        return self._finish(request_id, "cancelled")
