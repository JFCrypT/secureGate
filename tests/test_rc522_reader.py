from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry"))

from securegate.rfid.reader import RC522Reader


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.device = Mock()
        self.device.dev_read.return_value = 0x92
        self.device.pin_rst = 25
        self.device.request.return_value = (False, 16)
        self.device.anticoll.return_value = (False, [0, 1, 2, 3, 0])
        self.device.select_tag.return_value = False
        self.package = ModuleType("pirc522")
        self.package.RFID = Mock(return_value=self.device)
        self.module = ModuleType("pirc522.rfid")
        self.module.GPIO = Mock()
        self.module.GPIO.BCM = 11
        self.modules = patch.dict(sys.modules, {"pirc522": self.package, "pirc522.rfid": self.module})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    @patch("securegate.rfid.reader.time.sleep")
    def test_spi_wiring_uid_four_bytes_no_memory_write(self, _sleep):
        reader = RC522Reader()
        self.assertEqual(reader.poll(), "00010203")
        self.package.RFID.assert_called_once_with(bus=0, device=0, pin_rst=25, pin_irq=None, pin_mode=11)
        self.device.write.assert_not_called()
        reader.close()
        self.device.spi.close.assert_called_once()
        self.module.GPIO.cleanup.assert_called_once_with(25)

    @patch("securegate.rfid.reader.time.sleep")
    def test_seven_byte_uid_does_not_include_cascade_or_bcc(self, _sleep):
        self.device.anticoll.return_value = (False, [0x88, 4, 1, 2, 0x8F])
        self.device.anticoll2.return_value = (False, [3, 4, 5, 6, 4])
        self.assertEqual(RC522Reader().poll(), "04010203040506")

    @patch("securegate.rfid.reader.time.sleep")
    def test_cascade_three_rejected_instead_of_truncated_uid(self, _sleep):
        self.device.anticoll.return_value = (False, [0x88, 4, 1, 2, 0x8F])
        self.device.anticoll2.return_value = (False, [0x88, 3, 4, 5, 0x8A])
        with self.assertRaises(RuntimeError):
            RC522Reader().poll()

    @patch("securegate.rfid.reader.time.sleep")
    def test_no_card_returns_none_and_anticollision_failure_is_error(self, _sleep):
        reader = RC522Reader()
        self.device.request.return_value = (True, None)
        self.assertIsNone(reader.poll())
        self.device.request.return_value = (False, 16)
        self.device.anticoll.return_value = (True, [])
        with self.assertRaises(RuntimeError):
            reader.poll()

    def test_reader_disconnect_not_mistaken_for_card_removal(self):
        reader = RC522Reader()
        self.device.dev_read.return_value = 0xFF
        with self.assertRaises(RuntimeError):
            reader.poll()

    def test_invalid_chip_version_refuses_startup(self):
        self.device.dev_read.return_value = 0
        with self.assertRaises(RuntimeError):
            RC522Reader()
        self.device.spi.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
