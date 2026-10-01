"""Shared access decisions. Only credential denials count as failed attempts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import time

from securegate.alerts.schedule import is_restricted_time


@dataclass(frozen=True)
class AccessEvent:
    method: str
    user: str | None
    occurred_at: datetime
    image: object = None

    @property
    def granted(self):
        return self.user is not None


@dataclass(frozen=True)
class Alert:
    event: AccessEvent
    reasons: tuple
    failures: int

    def caption(self):
        result = f"Usuario: {self.event.user}" if self.event.granted else "No autorizado"
        zone = getattr(self.event.occurred_at.tzinfo, "key", str(self.event.occurred_at.tzinfo))
        return "\n".join([
            "🚨 ALERTA secureGate",
            *self.reasons,
            f"Horario: {self.event.occurred_at:%d/%m/%Y %H:%M:%S}",
            f"Zona horaria: {zone}",
            f"Método: {self.event.method}",
            f"Resultado: {result}",
            f"Rechazos consecutivos: {self.failures}",
        ])


class AccessController:
    """One controller per door, accessed by a single event consumer.

    Count mixed methods globally; successes reset the sequence. Failure alerts
    fire at 3, 6, 9... denials. Schedule deduplication must not suppress them.
    """

    def __init__(self, alert_cooldown=60.0, clock=time.monotonic):
        if not math.isfinite(alert_cooldown) or alert_cooldown < 0:
            raise ValueError("El cooldown debe ser finito y no negativo.")
        self.alert_cooldown = alert_cooldown
        self.clock = clock
        self.failures = 0
        self.last_schedule_alert = {}

    def process(self, event):
        restricted = is_restricted_time(event.occurred_at)
        self.failures = 0 if event.granted else self.failures + 1
        reasons = []
        if not event.granted and self.failures % 3 == 0:
            reasons.append("Tres intentos de ingreso fallidos consecutivos")
        key = (event.method, event.user)
        now = self.clock()
        previous = self.last_schedule_alert.get(key, float("-inf"))
        if restricted and now - previous >= self.alert_cooldown:
            reasons.append("Intento de ingreso fuera de horario")
        if not reasons:
            return None
        if restricted:
            # Combined alerts also refresh the schedule cooldown.
            self.last_schedule_alert[key] = now
        return Alert(event, tuple(reasons), self.failures)


class PresenceGate:
    """Rearm only after a reliable absence; read/transport errors are not absence."""

    def __init__(self, release_seconds=1.0, clock=time.monotonic):
        self.release_seconds = release_seconds
        self.clock = clock
        self.last_identity = None
        self.absent_since = None

    def observe(self, identity):
        now = self.clock()
        if identity is None:
            if self.absent_since is None:
                self.absent_since = now
            if now - self.absent_since >= self.release_seconds:
                self.last_identity = None
            return False
        self.absent_since = None
        if self.last_identity == identity:
            return False
        self.last_identity = identity
        return True
