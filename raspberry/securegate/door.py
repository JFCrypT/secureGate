"""Control seguro y configurable de la puerta.

El modo simulado es el predeterminado: permite probar todo el backend sin
energizar una cerradura. El modo GPIO sólo se habilita de forma explícita.
"""

from dataclasses import dataclass
import math
import time


class DoorControlError(RuntimeError):
    """La puerta no pudo completar una orden de apertura."""


@dataclass(frozen=True)
class DoorResult:
    status: str
    duration_seconds: float


def _validate_duration(value):
    duration = float(value)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("El tiempo de apertura debe ser finito y mayor que cero.")
    return duration


class SimulatedDoor:
    """Puerta para desarrollo: no utiliza GPIO ni afirma apertura física."""

    def __init__(self, duration_seconds=3.0):
        self.duration_seconds = _validate_duration(duration_seconds)

    def open(self):
        print(
            "[PUERTA] SIMULACIÓN: orden de apertura "
            f"durante {self.duration_seconds:g} s; GPIO sin activar.",
            flush=True,
        )
        return DoorResult("simulated", self.duration_seconds)

    def close(self):
        return None


class GPIORelayDoor:
    """Activa un módulo de relé desde un GPIO BCM de Raspberry Pi.

    La alimentación de la cerradura no pasa por el GPIO. El pin, la polaridad
    y el circuito de interfaz deben confirmarse antes de usar este modo.
    """

    def __init__(
        self,
        pin,
        active_high,
        duration_seconds=3.0,
        sleeper=time.sleep,
        gpio=None,
    ):
        if isinstance(pin, bool) or not isinstance(pin, int) or not 0 <= pin <= 27:
            raise ValueError("El pin del relé debe ser un número BCM entre 0 y 27.")
        self.pin = pin
        self.active_high = bool(active_high)
        self.duration_seconds = _validate_duration(duration_seconds)
        self.sleeper = sleeper

        if gpio is None:
            try:
                import RPi.GPIO as gpio
            except (ImportError, RuntimeError) as exc:
                raise DoorControlError(
                    "RPi.GPIO no está disponible. Usar --door-mode simulate "
                    "fuera de Raspberry Pi."
                ) from exc

        self.gpio = gpio
        self.active_level = gpio.HIGH if self.active_high else gpio.LOW
        self.inactive_level = gpio.LOW if self.active_high else gpio.HIGH

        try:
            gpio.setmode(gpio.BCM)
            gpio.setup(self.pin, gpio.OUT, initial=self.inactive_level)
        except Exception as exc:
            raise DoorControlError(
                f"No se pudo preparar GPIO{self.pin} para el relé."
            ) from exc

    def open(self):
        activated = False
        try:
            self.gpio.output(self.pin, self.active_level)
            activated = True
            print(
                f"[PUERTA] Relé activo en GPIO{self.pin} "
                f"durante {self.duration_seconds:g} s.",
                flush=True,
            )
            self.sleeper(self.duration_seconds)
        except Exception as exc:
            raise DoorControlError("Falló la orden física de apertura.") from exc
        finally:
            if activated:
                try:
                    self.gpio.output(self.pin, self.inactive_level)
                except Exception:
                    pass

        return DoorResult("opened", self.duration_seconds)

    def close(self):
        try:
            self.gpio.output(self.pin, self.inactive_level)
        finally:
            # Se libera únicamente el pin propio, no los GPIO del RC522/sensores.
            self.gpio.cleanup(self.pin)


def create_door(mode, pin=None, active_high=True, duration_seconds=3.0):
    if mode == "simulate":
        return SimulatedDoor(duration_seconds)
    if mode != "gpio":
        raise ValueError("Modo de puerta desconocido.")
    if pin is None:
        raise ValueError("--relay-pin es obligatorio con --door-mode gpio.")
    return GPIORelayDoor(pin, active_high, duration_seconds)
