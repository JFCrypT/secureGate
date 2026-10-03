import json
import time

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app import auth
from tests.conftest import PASSWORDS, TEST_SECRET, TEST_TOKEN, csrf_of, login
import cli


def test_sin_sesion_todo_redirige_al_login(client):
    for path in ("/dashboard/", "/dashboard/usuarios", "/dashboard/historial"):
        response = client.get(path)
        assert response.status_code == 303, path
        assert response.headers["location"] == "/dashboard/login"


def test_sin_sesion_htmx_recibe_hx_redirect(client):
    response = client.get("/dashboard/", headers={"HX-Request": "true"})
    assert response.status_code == 401
    assert response.headers["hx-redirect"] == "/dashboard/login"


def test_login_correcto_y_cookie(client):
    response = login(client, "admin")
    assert response.status_code == 303 and response.headers["location"] == "/dashboard/"
    cookie = response.headers["set-cookie"].lower()
    assert "securegate_session=" in cookie
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "secure" not in cookie.replace("securegate_session", "")
    page = client.get("/dashboard/")
    assert page.status_code == 200
    assert "admin · Administrador" in page.text


def test_la_cookie_no_lleva_secretos(client):
    response = login(client, "admin")
    cookie = response.headers["set-cookie"]
    assert TEST_TOKEN not in cookie and TEST_SECRET not in cookie
    page = client.get("/dashboard/").text
    assert TEST_TOKEN not in page and TEST_SECRET not in page


@pytest.mark.parametrize("username,password", [
    ("admin", "incorrecta"), ("nadie", "clave-admin-123"), ("", ""),
])
def test_login_incorrecto(client, username, password):
    response = client.post("/dashboard/login", data={
        "usuario": username, "clave": password, "csrf_token": csrf_of(client),
    })
    assert response.status_code == 401
    assert "Usuario o contraseña incorrectos." in response.text
    assert client.get("/dashboard/").status_code == 303


def test_login_sin_csrf_da_403(client):
    response = client.post("/dashboard/login", data={
        "usuario": "admin", "clave": PASSWORDS["admin"],
    })
    assert response.status_code == 403
    client.get("/dashboard/login")
    response = client.post("/dashboard/login", data={
        "usuario": "admin", "clave": PASSWORDS["admin"], "csrf_token": "otro",
    })
    assert response.status_code == 403


def test_csrf_por_header(admin):
    token = csrf_of(admin)
    assert admin.post("/dashboard/logout").status_code == 403
    assert admin.post("/dashboard/logout", headers={"X-CSRF-Token": token}).status_code == 303


def test_logout_limpia_la_sesion(admin):
    response = admin.post("/dashboard/logout", data={"csrf_token": csrf_of(admin)})
    assert response.status_code == 303 and response.headers["location"] == "/dashboard/login"
    assert admin.get("/dashboard/").status_code == 303


def test_rate_limit_bloquea_al_quinto_fallo(front, client):
    now = [1000.0]
    front.state.login_limiter = auth.LoginRateLimiter(clock=lambda: now[0])
    for _ in range(5):
        assert login(client, "admin", "mala").status_code == 401
    blocked = login(client, "admin")  # contraseña correcta, pero bloqueado
    assert blocked.status_code == 429 and "Demasiados intentos" in blocked.text
    now[0] += 301
    assert login(client, "admin").status_code == 303


def test_rate_limit_ventana_y_por_ip():
    now = [0.0]
    limiter = auth.LoginRateLimiter(clock=lambda: now[0])
    for _ in range(4):
        limiter.register_failure("10.0.0.1")
    now[0] += 301  # los fallos viejos salen de la ventana
    limiter.register_failure("10.0.0.1")
    assert limiter.blocked_seconds("10.0.0.1") == 0
    for _ in range(4):
        limiter.register_failure("10.0.0.1")
    assert limiter.blocked_seconds("10.0.0.1") == 300
    assert limiter.blocked_seconds("10.0.0.2") == 0


def test_sesion_vencida(front, admin, monkeypatch):
    real = time.time()
    monkeypatch.setattr(auth.time, "time", lambda: real + 8 * 3600 + 1)
    assert admin.get("/dashboard/").status_code == 303


def test_operador_deshabilitado_pierde_la_sesion(admin, operators_file):
    assert admin.get("/dashboard/").status_code == 200
    cli.main(["--file", str(operators_file), "disable-user", "admin"])
    assert admin.get("/dashboard/").status_code == 303
    assert login(admin, "admin").status_code == 401


def test_viewer_recibe_403_en_rutas_de_admin(front, client):
    @front.get("/dashboard/_solo_admin", dependencies=[Depends(auth.require_admin)])
    async def solo_admin():
        return {"ok": True}

    assert client.get("/dashboard/_solo_admin").status_code == 303
    login(client, "guardia")
    response = client.get("/dashboard/_solo_admin")
    assert response.status_code == 403 and "sólo para administradores" in response.text
    other = TestClient(front, follow_redirects=False)
    login(other, "admin")
    assert other.get("/dashboard/_solo_admin").json() == {"ok": True}


def test_archivo_de_operadores_ausente_o_roto(settings, api_transport):
    from app.main import create_app
    client = TestClient(create_app(settings, api_transport=api_transport), follow_redirects=False)
    assert login(client, "admin").status_code == 401
    settings.operators_file.write_text("{no es json", encoding="utf-8")
    assert login(client, "admin").status_code == 401


# --- cli.py -----------------------------------------------------------------

def run_cli(monkeypatch, path, *args, password="una-clave-larga"):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(password + "\n"))
    return cli.main(["--file", str(path), *args])


def test_cli_alta_cambio_y_baja(tmp_path, monkeypatch, capsys):
    path = tmp_path / "ops.json"
    run_cli(monkeypatch, path, "add-user", "Admin", "--role", "admin", "--password-stdin")
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    entry = json.loads(path.read_text())["usuarios"][0]
    assert entry["usuario"] == "admin" and entry["rol"] == "admin" and entry["activo"] is True
    assert entry["hash"].startswith("$2") and "una-clave-larga" not in path.read_text()

    store = auth.OperatorStore(path)
    assert store.verify("admin", "una-clave-larga")["rol"] == "admin"
    assert store.verify("admin", "otra") is None

    run_cli(monkeypatch, path, "set-password", "admin", "--password-stdin", password="clave-nueva-456")
    assert auth.OperatorStore(path).verify("admin", "clave-nueva-456")
    run_cli(monkeypatch, path, "disable-user", "admin")
    assert auth.OperatorStore(path).verify("admin", "clave-nueva-456") is None
    run_cli(monkeypatch, path, "enable-user", "admin")
    run_cli(monkeypatch, path, "list")
    out = capsys.readouterr().out
    assert "admin\tadmin\tactivo" in out and "$2" not in out


def test_cli_rechaza_duplicados_y_claves_cortas(tmp_path, monkeypatch):
    path = tmp_path / "ops.json"
    run_cli(monkeypatch, path, "add-user", "admin", "--role", "admin", "--password-stdin")
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, path, "add-user", "admin", "--role", "viewer", "--password-stdin")
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, path, "add-user", "otro", "--role", "viewer", "--password-stdin", password="corta")
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, path, "add-user", "Nombre Inválido", "--role", "viewer", "--password-stdin")
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, path, "disable-user", "nadie")
