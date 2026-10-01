from datetime import datetime
from pathlib import Path
from queue import Queue
from threading import Event
from unittest.mock import Mock, patch
import sys
import sqlite3
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry"))

from securegate.access import AccessEvent, PresenceGate
from securegate.alerts.schedule import load_timezone
from runtime_access import face_worker, rfid_worker


class NoFace(RuntimeError):
    pass


class WorkersTests(unittest.TestCase):
    def setUp(self):
        self.queue = Queue()
        self.stop = Event()
        self.now = [0.0]
        self.zone = load_timezone()

    def decisions(self):
        output = []
        while not self.queue.empty():
            event = self.queue.get_nowait()
            if isinstance(event, AccessEvent):
                output.append(event)
        return output

    def test_rfid_held_card_not_counted_repeatedly_and_fault_not_denial(self):
        samples = iter(["A", "A", OSError(), None, None, "A", "B"])
        def poll():
            self.now[0] += 1
            try:
                value = next(samples)
            except StopIteration:
                self.stop.set()
                return None
            if isinstance(value, Exception):
                raise value
            return value
        reader = Mock()
        reader.poll.side_effect = poll
        registry = Mock()
        registry.authorize.side_effect = [None, None, "user_001"]
        with patch("runtime_access.PresenceGate", return_value=PresenceGate(clock=lambda: self.now[0])):
            rfid_worker(reader, registry, self.queue, self.stop, self.zone, interval=0)
        events = self.decisions()
        self.assertEqual([event.user for event in events], [None, None, "user_001"])
        self.assertEqual(registry.authorize.call_count, 3)
        reader.close.assert_called_once()

    def test_database_fault_is_not_a_failed_attempt(self):
        reader = Mock()
        polls = [0]
        def poll():
            polls[0] += 1
            if polls[0] > 1:
                self.stop.set()
                return None
            return "A"
        reader.poll.side_effect = poll
        registry = Mock()
        registry.authorize.side_effect = sqlite3.OperationalError("database unavailable")
        rfid_worker(reader, registry, self.queue, self.stop, self.zone, interval=0)
        self.assertEqual(self.decisions(), [])
        registry.authorize.assert_called_once()

    def test_face_held_and_camera_fault_not_extra_attempts(self):
        samples = iter(["face"] * 5 + [OSError(), NoFace(), NoFace()] + ["face"] * 3)
        source = Mock()
        source.no_face_error = NoFace
        def capture():
            self.now[0] += 1
            try:
                value = next(samples)
            except StopIteration:
                self.stop.set()
                raise OSError()
            if isinstance(value, OSError):
                raise value
            return value
        def match(image):
            if isinstance(image, NoFace):
                raise image
            return ("user_001", 0.1)
        source.capture.side_effect = capture
        source.match.side_effect = match
        source.decide.return_value = (None, "photo")
        with patch("runtime_access.PresenceGate", return_value=PresenceGate(clock=lambda: self.now[0])):
            face_worker(source, self.queue, self.stop, self.zone, interval=0, cooldown=0)
        events = self.decisions()
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event.user is None for event in events))
        self.assertEqual(source.decide.call_count, 2)


if __name__ == "__main__":
    unittest.main()
