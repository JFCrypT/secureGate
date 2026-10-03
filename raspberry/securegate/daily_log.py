"""Log diario en archivo plano, rotado por fecha local.

Cada día se usa ``logs/securegate-AAAA-MM-DD.log``. El runtime escribe aquí
los mismos eventos que muestra por consola y el comando Telegram ``/logs``
lee el archivo del día en curso.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock


class DailyLogger:
    """Escritura thread-safe con rotación por fecha local."""

    def __init__(self, log_dir, timezone, prefix="securegate"):
        self.log_dir = Path(log_dir)
        self.timezone = timezone
        self.prefix = prefix
        self._lock = Lock()
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _now(self, moment=None):
        if moment is None:
            return datetime.now(self.timezone)
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("moment debe incluir zona horaria.")
        return moment.astimezone(self.timezone)

    def path_for(self, moment=None):
        day = self._now(moment).date().isoformat()
        return self.log_dir / f"{self.prefix}-{day}.log"

    def write(self, level, message, moment=None):
        stamped = self._now(moment)
        line = f"[{stamped:%Y-%m-%d %H:%M:%S%z}] [{level}] {message}\n"
        path = self.path_for(stamped)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(line)
        return line

    def read_today(self, limit=50, moment=None):
        """Devuelve (líneas, total). Vacío si el archivo no existe."""
        if limit < 1:
            raise ValueError("limit debe ser mayor que cero.")
        path = self.path_for(moment)
        try:
            with path.open("r", encoding="utf-8") as stream:
                lines = stream.read().splitlines()
        except FileNotFoundError:
            return [], 0
        total = len(lines)
        return lines[-limit:], total

    def today_label(self, moment=None):
        return self._now(moment).date().isoformat()
