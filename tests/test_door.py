from pathlib import Path
from unittest.mock import Mock, call
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry"))

from securegate.door import (
    DoorControlError,
    GPIORelayDoor,
    SimulatedDoor,
    create_door,
)


class DoorTests(unittest.TestCase):
    def gpio(self):
        gpio = Mock()
        gpio.HIGH = 1
        gpio.LOW = 0
        gpio.BCM = 11
        gpio.OUT = 1
        return gpio

    def test_simulation_never_imports_or_uses_gpio(self):
        door = SimulatedDoor(3)
        result = door.open()
        self.assertEqual(result.status, "simulated")
        self.assertEqual(result.duration_seconds, 3)

    def test_active_high_relay_returns_to_safe_level(self):
        gpio = self.gpio()
        sleeper = Mock()
        door = GPIORelayDoor(5, True, 2.5, sleeper=sleeper, gpio=gpio)
        gpio.setup.assert_called_once_with(5, gpio.OUT, initial=gpio.LOW)
        result = door.open()
        self.assertEqual(result.status, "opened")
        self.assertEqual(gpio.output.call_args_list, [call(5, gpio.HIGH), call(5, gpio.LOW)])
        sleeper.assert_called_once_with(2.5)
        door.close()
        gpio.cleanup.assert_called_once_with(5)

    def test_active_low_relay_uses_inverse_levels(self):
        gpio = self.gpio()
        door = GPIORelayDoor(6, False, 1, sleeper=Mock(), gpio=gpio)
        gpio.setup.assert_called_once_with(6, gpio.OUT, initial=gpio.HIGH)
        door.open()
        self.assertEqual(gpio.output.call_args_list, [call(6, gpio.LOW), call(6, gpio.HIGH)])

    def test_failure_attempts_to_deactivate_relay(self):
        gpio = self.gpio()
        door = GPIORelayDoor(
            5,
            True,
            1,
            sleeper=Mock(side_effect=OSError("interrupted")),
            gpio=gpio,
        )
        with self.assertRaises(DoorControlError):
            door.open()
        self.assertEqual(gpio.output.call_args_list[-1], call(5, gpio.LOW))

    def test_gpio_mode_requires_explicit_pin(self):
        with self.assertRaises(ValueError):
            create_door("gpio")
        with self.assertRaises(ValueError):
            SimulatedDoor(0)


if __name__ == "__main__":
    unittest.main()
