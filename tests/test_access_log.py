from datetime import datetime
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry"))

from securegate.access import AccessEvent
from securegate.access_log import AccessLogRepository
from securegate.alerts.schedule import load_timezone


class AccessLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "securegate.db"
        self.database.touch()
        self.repository = AccessLogRepository(self.database)
        self.moment = datetime(2026, 10, 1, 22, 30, tzinfo=load_timezone())

    def rows(self):
        with sqlite3.connect(self.database) as connection:
            return connection.execute(
                """SELECT method, external_id, granted, restricted_time,
                          alert_reasons, door_status
                   FROM access_events ORDER BY event_id"""
            ).fetchall()

    def test_records_authorized_out_of_hours_simulation(self):
        event = AccessEvent("RFID", "user_001", self.moment)
        event_id = self.repository.record(
            event,
            True,
            ("Intento de ingreso fuera de horario",),
            "simulated",
        )
        self.assertEqual(event_id, 1)
        self.assertEqual(
            self.rows(),
            [(
                "RFID",
                "user_001",
                1,
                1,
                "Intento de ingreso fuera de horario",
                "simulated",
            )],
        )

    def test_records_denial_without_door_order(self):
        event = AccessEvent("facial", None, self.moment.replace(hour=12))
        self.repository.record(event, False)
        self.assertEqual(self.rows()[0][1:], (None, 0, 0, "", "not_requested"))

    def test_rejects_naive_datetime_and_unknown_door_status(self):
        with self.assertRaises(ValueError):
            self.repository.record(
                AccessEvent("RFID", None, datetime(2026, 10, 1, 12)),
                False,
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.record(
                AccessEvent("RFID", None, self.moment),
                False,
                door_status="invented",
            )


if __name__ == "__main__":
    unittest.main()
