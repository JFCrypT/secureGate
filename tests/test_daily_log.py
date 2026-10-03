from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry"))

from securegate.alerts.commands import (
    build_logs_text,
    is_authorized,
    parse_command,
    parse_limit,
)
from securegate.alerts.schedule import load_timezone
from securegate.daily_log import DailyLogger


class DailyLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        try:
            self.tz = load_timezone()
        except ValueError:
            # Windows sin tzdata: usar UTC para verificación local.
            # En Raspberry Pi (Linux) load_timezone funciona.
            from datetime import timezone
            self.tz = timezone.utc
        self.logger = DailyLogger(Path(self.temp.name) / "logs", self.tz)

    def test_rotates_by_local_date(self):
        morning = datetime(2026, 10, 3, 0, 5, tzinfo=self.tz)
        night = datetime(2026, 10, 3, 23, 59, tzinfo=self.tz)
        next_day = datetime(2026, 10, 4, 0, 1, tzinfo=self.tz)
        self.logger.write("ACCESO", " facial: USUARIO VÁLIDO user_001", moment=morning)
        self.logger.write("ALERTA", "Tres intentos fallidos", moment=night)
        self.logger.write("INFO", "otro día", moment=next_day)
        today = self.logger.path_for(morning)
        self.assertTrue(today.name.endswith("2026-10-03.log"))
        lines, total = self.logger.read_today(limit=50, moment=night)
        self.assertEqual(total, 2)
        self.assertEqual(len(lines), 2)
        other_lines, other_total = self.logger.read_today(limit=50, moment=next_day)
        self.assertEqual(other_total, 1)

    def test_read_missing_file_returns_empty(self):
        lines, total = self.logger.read_today(limit=10)
        self.assertEqual((lines, total), ([], 0))

    def test_build_logs_text_includes_summary(self):
        moment = datetime(2026, 10, 3, 12, 0, tzinfo=self.tz)
        self.logger.write("ACCESO", "RFID: USUARIO VÁLIDO user_001", moment=moment)

        class FakeAccessLog:
            def summary(self, date_prefix=None):
                self.seen = date_prefix
                return {"total": 1, "granted": 1, "denied": 0, "restricted": 0}

        fake = FakeAccessLog()
        text = build_logs_text(self.logger, fake, limit=50, moment=moment)
        self.assertIn("2026-10-03", text)
        self.assertIn("USUARIO VÁLIDO", text)
        self.assertIn("Resumen DB", text)
        self.assertEqual(fake.seen, "2026-10-03")


class CommandParsingTests(unittest.TestCase):
    def test_parse_logs_with_bot_suffix_and_limit(self):
        command, arg = parse_command("/logs@securegate_bot 100")
        self.assertEqual(command, "/logs")
        self.assertEqual(parse_limit(arg), 100)

    def test_parse_limit_clamps(self):
        self.assertEqual(parse_limit("", default=50), 50)
        self.assertEqual(parse_limit("not-a-number", default=50), 50)
        self.assertEqual(parse_limit("500"), 200)
        self.assertEqual(parse_limit("0"), 1)

    def test_only_expected_chat_is_authorized(self):
        update = {"message": {"chat": {"id": 123}, "text": "/logs"}}
        self.assertTrue(is_authorized(update, "123"))
        self.assertFalse(is_authorized(update, "999"))

    def test_non_command_returns_none(self):
        self.assertEqual(parse_command("hola"), (None, None))


if __name__ == "__main__":
    unittest.main()
