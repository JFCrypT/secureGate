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


# --- Front ------------------------------------------------------------------

PASSWORDS = {"admin": "clave-admin-123", "guardia": "clave-guardia-123"}


@pytest.fixture(scope="session")
def operator_hashes():
    from app.auth import hash_password
    # rounds=4: bcrypt rápido, sólo para tests.
    return {name: hash_password(password, rounds=4) for name, password in PASSWORDS.items()}


@pytest.fixture
def operators_file(settings, operator_hashes):
    from app.auth import write_operators_file
    write_operators_file(settings.operators_file, {"usuarios": [
        {"usuario": "admin", "hash": operator_hashes["admin"], "rol": "admin", "activo": True},
        {"usuario": "guardia", "hash": operator_hashes["guardia"], "rol": "viewer", "activo": True},
    ]})
    return settings.operators_file


@pytest.fixture
def front(settings, operators_file, api_transport):
    from app.main import create_app
    return create_app(settings, api_transport=api_transport)


@pytest.fixture
def client(front):
    from fastapi.testclient import TestClient
    return TestClient(front, follow_redirects=False)


def csrf_of(client):
    """Token CSRF de la sesión actual, leído del HTML como lo haría el navegador."""
    import re
    page = client.get("/dashboard/login", follow_redirects=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', page.text).group(1)


def login(client, username="admin", password=None):
    response = client.post("/dashboard/login", data={
        "usuario": username,
        "clave": PASSWORDS[username] if password is None else password,
        "csrf_token": csrf_of(client),
    })
    return response


@pytest.fixture
def admin(client):
    assert login(client, "admin").status_code == 303
    return client


@pytest.fixture
def viewer(client):
    assert login(client, "guardia").status_code == 303
    return client
