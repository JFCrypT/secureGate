from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry"))

from securegate.access import AccessController, AccessEvent, PresenceGate
from securegate.alerts.schedule import load_timezone
from runtime_access import deliver_alert


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.now = [0.0]
        self.controller = AccessController(clock=lambda: self.now[0])
        self.moment = datetime(2026, 10, 1, 12, tzinfo=load_timezone())

    def event(self, method="facial", user=None, image=None):
        return AccessEvent(method, user, self.moment, image)

    def test_three_mixed_denials_alert_during_allowed_hours(self):
        self.assertIsNone(self.controller.process(self.event("RFID")))
        self.assertIsNone(self.controller.process(self.event()))
        alert = self.controller.process(self.event("RFID"))
        self.assertEqual(alert.failures, 3)
        self.assertIn("Tres intentos", alert.caption())
        self.assertIn("Método: RFID", alert.caption())
        self.assertIn("01/10/2026 12:00:00", alert.caption())

    def test_success_by_either_method_resets_mixed_sequence(self):
        for method in ("facial", "RFID"):
            with self.subTest(method=method):
                self.controller.process(self.event())
                self.controller.process(self.event("RFID"))
                self.assertIsNone(self.controller.process(self.event(method, "user_001")))
                self.assertEqual(self.controller.failures, 0)
                self.assertIsNone(self.controller.process(self.event("RFID")))
                self.assertIsNone(self.controller.process(self.event()))
                self.assertIsNotNone(self.controller.process(self.event("RFID")))
                self.controller.process(self.event(method, "user_001"))

    def test_failure_alert_not_suppressed_by_schedule_cooldown(self):
        self.moment = self.moment.replace(hour=22)
        first = self.controller.process(self.event("RFID"))
        self.assertIn("fuera de horario", first.caption())
        self.assertIsNone(self.controller.process(self.event("RFID")))
        third = self.controller.process(self.event("RFID"))
        self.assertIn("Tres intentos", third.caption())
        self.assertEqual(self.controller.failures, 3)

    def test_both_reasons_combine_in_one_alert(self):
        self.controller.process(self.event())
        self.controller.process(self.event())
        self.moment = self.moment.replace(hour=21)
        alert = self.controller.process(self.event())
        self.assertEqual(len(alert.reasons), 2)

    def test_repeat_failure_alert_every_three(self):
        alerts = [self.controller.process(self.event()) for _ in range(7)]
        self.assertEqual([a.failures for a in alerts if a], [3, 6])

    def test_success_does_not_skip_out_of_hours_alert(self):
        self.moment = self.moment.replace(hour=22)
        self.assertIsNotNone(self.controller.process(self.event("RFID", "user_001")))
        self.assertEqual(self.controller.failures, 0)

    def test_schedule_cooldown_uses_elapsed_time_and_method(self):
        self.moment = self.moment.replace(hour=22)
        self.assertIsNotNone(self.controller.process(self.event("RFID", "user_001")))
        self.assertIsNone(self.controller.process(self.event("RFID", "user_001")))
        self.assertIsNotNone(self.controller.process(self.event("facial", "user_001")))
        self.now[0] = 60
        self.assertIsNotNone(self.controller.process(self.event("RFID", "user_001")))

    def test_presence_counts_one_presentation_until_removed(self):
        gate = PresenceGate(clock=lambda: self.now[0])
        self.assertTrue(gate.observe("A"))
        self.assertFalse(gate.observe("A"))
        self.now[0] = 1
        gate.observe(None)
        self.now[0] = 1.2
        self.assertFalse(gate.observe("A"))  # brief radio dropout
        gate.observe(None)
        self.now[0] = 2.3
        gate.observe(None)
        self.assertTrue(gate.observe("A"))
        self.assertTrue(gate.observe("B"))  # another card is a new attempt

    def test_text_fallback_when_camera_unavailable(self):
        notifier = Mock()
        alert = self.controller.process(self.event())
        self.controller.process(self.event())
        alert = self.controller.process(self.event())
        deliver_alert(notifier, alert, capture=Mock(side_effect=RuntimeError()))
        notifier.send_message.assert_called_once()
        self.assertIn("Foto no disponible", notifier.send_message.call_args.args[0])
        notifier.send_photo.assert_not_called()

    def test_photo_failure_falls_back_to_text(self):
        notifier = Mock()
        notifier.send_photo.side_effect = RuntimeError("encoding failed")
        self.controller.process(self.event())
        self.controller.process(self.event())
        alert = self.controller.process(self.event(image=object()))
        deliver_alert(notifier, alert)
        notifier.send_message.assert_called_once()

    def test_rfid_alert_takes_photo_only_for_notification(self):
        notifier = Mock()
        capture = Mock(return_value="frame")
        self.controller.process(self.event("RFID"))
        self.controller.process(self.event("RFID"))
        alert = self.controller.process(self.event("RFID"))
        deliver_alert(notifier, alert, capture)
        capture.assert_called_once()
        notifier.send_photo.assert_called_once()
        self.assertEqual(notifier.send_photo.call_args.args[0], "frame")


if __name__ == "__main__":
    unittest.main()
