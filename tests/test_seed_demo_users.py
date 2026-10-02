import sqlite3
import tempfile
import unittest
from pathlib import Path

from admin.seed_demo_users import demo_users, seed
from raspberry.init_db import SCHEMA, apply_migrations


class SeedDemoUsersTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = Path(self.tempdir.name) / "securegate.db"
        with sqlite3.connect(self.database) as connection:
            connection.executescript(SCHEMA)
            apply_migrations(connection)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_creates_twenty_users_and_is_idempotent(self):
        planned = demo_users()
        self.assertEqual(len(planned), 20)
        self.assertEqual(
            sum(user["credential_plan"] == "RFID" for user in planned), 10
        )
        self.assertEqual(
            sum(user["credential_plan"] == "RFID + facial" for user in planned),
            10,
        )

        created, existing = seed(self.database)
        self.assertEqual((len(created), len(existing)), (20, 0))

        created, existing = seed(self.database)
        self.assertEqual((len(created), len(existing)), (0, 20))

        with sqlite3.connect(self.database) as connection:
            count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            credential_count = connection.execute(
                "SELECT COUNT(*) FROM biometric_templates"
            ).fetchone()[0]
        self.assertEqual(count, 20)
        self.assertEqual(credential_count, 0)


if __name__ == "__main__":
    unittest.main()
