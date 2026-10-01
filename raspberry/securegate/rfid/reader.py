"""Adapter for pi-rc522 2.3.0 (Raspberry Pi 3/4, SPI0, no IRQ).

No card memory is written. A UID is an identifier, not clone-resistant proof.
"""

from securegate.rfid.registry import normalize_uid
import time


class RC522Reader:
    def __init__(self):
        try:
            from pirc522 import RFID
            from pirc522.rfid import GPIO
            self.device = RFID(
                bus=0, device=0, pin_rst=25, pin_irq=None, pin_mode=GPIO.BCM
            )
        except (ImportError, OSError, RuntimeError) as exc:
            raise RuntimeError(
                "No se pudo iniciar RC522. Revisar requirements-rfid.txt, "
                "SPI habilitado, permisos y cableado de docs/INSTALACION_RFID.md."
            ) from exc
        version = self.device.dev_read(0x37)
        if version not in (0x91, 0x92, 0x88):
            self.close()
            raise RuntimeError(
                f"RC522 no responde con una versión admitida (0x{version:02X}). "
                "Revisar cableado; no se habilita el acceso."
            )

    def poll(self):
        try:
            if self.device.dev_read(0x37) not in (0x91, 0x92, 0x88):
                raise RuntimeError("Se perdió la comunicación SPI con RC522.")
            # Reset the RF field each poll to bring 4/7-byte tags back to IDLE.
            # This prevents HALT/ACTIVE states from masquerading as card removal.
            self.device.set_antenna(False)
            time.sleep(0.005)
            self.device.set_antenna(True)
            time.sleep(0.005)
            error, _tag_type = self.device.request()
            if error:
                return None
            error, uid = self.device.anticoll()
            if error:
                raise RuntimeError("UID ilegible o varias tarjetas sobre el lector.")
            if uid[0] != 0x88:
                return normalize_uid(uid[:4])
            if self.device.select_tag(uid):
                raise RuntimeError("No se pudo seleccionar la tarjeta de 7 bytes.")
            error, tail = self.device.anticoll2()
            if error or tail[0] == 0x88:
                raise RuntimeError("UID ilegible o longitud no admitida (usar 4 o 7 bytes).")
            return normalize_uid(uid[1:4] + tail[:4])
        except (OSError, ValueError) as exc:
            raise RuntimeError("Falló la lectura del RC522.") from exc

    def close(self):
        # Only release our RST line. Avoid library.cleanup(): it cleans all GPIO,
        # including the relay/sensors owned by other groups.
        try:
            self.device.set_antenna(False)
        finally:
            try:
                self.device.spi.close()
            finally:
                from pirc522.rfid import GPIO
                GPIO.cleanup(self.device.pin_rst)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
