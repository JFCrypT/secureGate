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
from securegate.runtime_status import RuntimeStatusRepository


class RuntimeStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "securegate.db"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(SCHEMA)
        self.now = [datetime(2026, 10, 2, 15, tzinfo=timezone.utc)]
        self.repository = RuntimeStatusRepository(
            self.database, clock=lambda: self.now[0]
        )

    def test_running_stale_and_stopped_states(self):
        self.assertFalse(self.repository.get()["online"])
        self.repository.update("running", "both", "simulate")
        current = self.repository.get()
        self.assertTrue(current["online"])
        self.assertEqual(current["methods"], "both")
        self.now[0] += timedelta(seconds=16)
        self.assertFalse(self.repository.get()["online"])
        self.repository.update("stopped", "both", "simulate")
        self.assertFalse(self.repository.get()["online"])
        self.assertEqual(self.repository.get()["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
