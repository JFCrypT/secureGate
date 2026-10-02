from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry"))

from init_db import SCHEMA
from securegate.rfid.enrollment import (
    EnrollmentBusy,
    EnrollmentConflict,
    EnrollmentNotFound,
    RFIDEnrollmentRepository,
)
from securegate.users import UserRepository


class RFIDEnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "securegate.db"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(SCHEMA)
        UserRepository(self.database).create("user_001")
        UserRepository(self.database).create("user_002")
        self.now = [datetime(2026, 10, 2, 15, tzinfo=timezone.utc)]
        self.repository = RFIDEnrollmentRepository(
            self.database, clock=lambda: self.now[0]
        )

    def test_only_one_pending_request_and_completion(self):
        request = self.repository.create("user_001", 60)
        self.assertEqual(request["status"], "pending")
        with self.assertRaises(EnrollmentBusy):
            self.repository.create("user_002", 60)
        completed = self.repository.complete(request["request_id"])
        self.assertEqual(completed["status"], "completed")
        self.assertIsNone(self.repository.pending())

    def test_request_expires_without_card(self):
        request = self.repository.create("user_001", 10)
        self.now[0] += timedelta(seconds=11)
        expired = self.repository.get(request["request_id"])
        self.assertEqual(expired["status"], "expired")
        with self.assertRaises(EnrollmentNotFound):
            self.repository.cancel(request["request_id"])

    def test_inactive_or_existing_card_rejected(self):
        users = UserRepository(self.database)
        users.set_active("user_001", False)
        with self.assertRaises(EnrollmentConflict):
            self.repository.create("user_001")
        users.set_active("user_001", True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS rfid_credentials (
                    credential_id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    uid_digest TEXT NOT NULL UNIQUE,
                    active INTEGER NOT NULL
                )"""
            )
            connection.execute(
                """INSERT INTO rfid_credentials(user_id, uid_digest, active)
                   VALUES (1, 'digest', 1)"""
            )
        with self.assertRaises(EnrollmentConflict):
            self.repository.create("user_001")


if __name__ == "__main__":
    unittest.main()
