from datetime import datetime
from pathlib import Path
import sys
import unittest


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "raspberry"))

from securegate.alerts.schedule import (
    is_restricted_time,
    load_timezone,
)


class RestrictedScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.timezone = load_timezone()

    def local_time(self, year, month, day, hour, minute=0):
        return datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=self.timezone,
        )

    def test_weekday_restricted_period_boundaries(self):
        monday = (2026, 9, 28)

        self.assertTrue(
            is_restricted_time(
                self.local_time(*monday, 5, 59)
            )
        )
        self.assertFalse(
            is_restricted_time(
                self.local_time(*monday, 6, 0)
            )
        )
        self.assertFalse(
            is_restricted_time(
                self.local_time(*monday, 20, 59)
            )
        )
        self.assertTrue(
            is_restricted_time(
                self.local_time(*monday, 21, 0)
            )
        )

    def test_weekend_restricted_period_boundaries(self):
        saturday = (2026, 10, 3)
        sunday = (2026, 10, 4)

        for day in (saturday, sunday):
            with self.subTest(day=day):
                self.assertTrue(
                    is_restricted_time(
                        self.local_time(*day, 8, 59)
                    )
                )
                self.assertFalse(
                    is_restricted_time(
                        self.local_time(*day, 9, 0)
                    )
                )
                self.assertFalse(
                    is_restricted_time(
                        self.local_time(*day, 16, 59)
                    )
                )
                self.assertTrue(
                    is_restricted_time(
                        self.local_time(*day, 17, 0)
                    )
                )

    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValueError):
            is_restricted_time(
                datetime(2026, 9, 28, 21, 0)
            )


if __name__ == "__main__":
    unittest.main()
