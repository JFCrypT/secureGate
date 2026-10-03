from datetime import datetime, timezone
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402
from dev.mock_api import create_mock_app  # noqa: E402


# Valores de prueba, no credenciales reales.
TEST_TOKEN = "token-de-prueba-" + "x" * 32
TEST_SECRET = "secreto-de-prueba-" + "y" * 32
API_URL = "http://api.test"


class FakeClock:
    """Reloj controlable para el mock (heartbeat, enrolamientos)."""

    def __init__(self):
        self.moment = datetime(2026, 10, 3, 15, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.moment

    def advance(self, seconds):
        from datetime import timedelta
        self.moment += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def mock_api(clock):
    """API falsa en memoria, sin generador de eventos."""
    return create_mock_app(TEST_TOKEN, clock=clock)


@pytest.fixture
def mock_state(mock_api):
    return mock_api.state.mock


@pytest.fixture
def api_transport(mock_api):
    return httpx.ASGITransport(app=mock_api)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        api_url=API_URL,
        api_token=TEST_TOKEN,
        session_secret=TEST_SECRET,
        operators_file=tmp_path / "operators.json",
    )
