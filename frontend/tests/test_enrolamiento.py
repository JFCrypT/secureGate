import re

import httpx
import pytest

from tests.conftest import api_responds, csrf_of


START = "/dashboard/usuarios/user_002/rfid"


def post(client, path, **data):
    data["csrf_token"] = csrf_of(client)
    return client.post(path, data=data)


def start(client, path=START):
    response = post(client, path)
    assert response.status_code == 303, response.text
    return response.headers["location"]


def test_pantalla_inicial(admin):
    page = admin.get(START)
    assert page.status_code == 200
    assert "Bruno Gómez (user_002)" in page.text and "Iniciar" in page.text
    assert "lector RFID no está activo" not in page.text


def test_usuario_inactivo_se_bloquea(admin):
    text = admin.get("/dashboard/usuarios/user_004/rfid").text
    assert "Activá el usuario primero" in text and "Iniciar" not in text


def test_usuario_con_tarjeta_se_bloquea(admin):
    text = admin.get("/dashboard/usuarios/user_001/rfid").text
    assert "Revocá la tarjeta actual primero" in text and "Iniciar" not in text


@pytest.mark.parametrize("setup", [{"offline": "1"}, {"methods": "face"}, {"offline": "unknown"}])
def test_lector_inactivo_avisa_pero_deja_continuar(admin, mock_state, setup):
    for name, value in setup.items():
        setattr(mock_state, name, value)
    text = admin.get(START).text
    assert "El lector RFID no está activo; la solicitud va a expirar" in text
    assert "Iniciar" in text


def test_espera_con_cuenta_regresiva_y_completa(admin, mock_state, clock):
    location = start(admin)
    assert re.fullmatch(r"/dashboard/usuarios/user_002/rfid/\d+", location)
    request_id = location.rsplit("/", 1)[1]
    page = admin.get(location).text
    assert "Acercá la tarjeta al lector" in page
    assert 'hx-trigger="every 1s"' in page and f"/partials/enrolamiento/{request_id}" in page
    assert re.search(r'class="countdown"[^>]*>\d+ s<', page)
    assert "Cancelar" in page

    clock.advance(6)
    partial = admin.get(f"/dashboard/partials/enrolamiento/{request_id}").text
    assert "Tarjeta asociada a Bruno Gómez" in partial
    assert "hx-trigger" not in partial  # deja de consultar
    assert "uid" not in partial.lower()
    assert "Sí" in admin.get("/dashboard/usuarios?q=user_002&tarjeta=si").text


def test_cuenta_regresiva_sale_de_expires_at(admin, front):
    from datetime import timedelta
    from app import timefmt
    enrollment = {
        "request_id": 3, "external_id": "user_002", "status": "pending",
        "created_at": timefmt.now_utc().isoformat(),
        "expires_at": (timefmt.now_utc() + timedelta(seconds=42)).isoformat(),
        "finished_at": None, "error_code": None,
    }

    def handler(request):
        if "rfid-enrollments" in request.url.path:
            return httpx.Response(200, json=enrollment)
        return httpx.Response(200, json=[])

    with api_responds(front, handler):
        text = admin.get("/dashboard/partials/enrolamiento/3").text
    assert re.search(r">4[12] s<", text)


def test_tarjeta_de_otro_usuario(admin, mock_state, clock):
    mock_state.enroll = "failed"
    location = start(admin)
    clock.advance(6)
    text = admin.get(location).text
    assert "No se pudo asociar la tarjeta. Puede que ya pertenezca a otro usuario." in text
    assert "Intentar de nuevo" in text
    assert mock_state.find_user("user_002")["has_rfid"] is False


def test_expira_sin_tarjeta(admin, mock_state, clock):
    mock_state.enroll = "expired"
    location = start(admin)
    clock.advance(61)
    assert "No se detectó ninguna tarjeta a tiempo." in admin.get(location).text


def test_cancelar(admin, mock_state):
    location = start(admin)
    response = post(admin, f"{location}/cancelar")
    assert response.status_code == 303 and response.headers["location"] == location
    assert "Solicitud cancelada." in admin.get(location).text
    assert mock_state.enrollments[-1]["status"] == "cancelled"
    # Cancelar algo que ya terminó no rompe: muestra en qué quedó.
    assert post(admin, f"{location}/cancelar").status_code == 303


def test_409_por_otra_solicitud_pendiente_ofrece_reintentar(admin):
    start(admin, "/dashboard/usuarios/user_006/rfid")
    response = post(admin, START)
    assert response.status_code == 409
    assert "Ya existe otra solicitud de enrolamiento pendiente." in response.text
    assert "Reintentar" in response.text


def test_409_si_ya_tiene_tarjeta_o_esta_inactivo(admin):
    response = post(admin, "/dashboard/usuarios/user_001/rfid")
    assert response.status_code == 409 and "revocarla primero" in response.text
    response = post(admin, "/dashboard/usuarios/user_004/rfid")
    assert response.status_code == 409 and "El usuario está deshabilitado." in response.text


def test_no_retoma_una_solicitud_pendiente(admin):
    start(admin)
    text = admin.get(START).text
    assert "Iniciar" in text and "Acercá la tarjeta" not in text


def test_usuario_o_solicitud_inexistente(admin):
    assert admin.get("/dashboard/usuarios/user_999/rfid").status_code == 404
    assert post(admin, "/dashboard/usuarios/user_999/rfid").status_code == 404
    assert admin.get("/dashboard/usuarios/user_002/rfid/99").status_code == 404
    assert admin.get("/dashboard/partials/enrolamiento/99").status_code == 404
    location = start(admin)
    other = location.replace("user_002", "user_006")
    assert admin.get(other).status_code == 404  # la solicitud es de otro usuario


def test_corte_de_api_durante_la_espera_sigue_consultando(admin, front):
    location = start(admin)
    request_id = location.rsplit("/", 1)[1]
    with api_responds(front, httpx.ConnectError("x")):
        partial = admin.get(f"/dashboard/partials/enrolamiento/{request_id}")
    assert partial.status_code == 200
    assert "API no disponible" in partial.text and 'hx-trigger="every 1s"' in partial.text


@pytest.mark.parametrize("method,path", [
    ("get", START), ("post", START), ("get", START + "/1"),
    ("post", START + "/1/cancelar"), ("get", "/dashboard/partials/enrolamiento/1"),
])
def test_viewer_no_enrola(viewer, mock_state, method, path):
    data = {"csrf_token": csrf_of(viewer)}
    response = viewer.get(path) if method == "get" else viewer.post(path, data=data)
    assert response.status_code == 403
    assert mock_state.enrollments == []


def test_iniciar_sin_csrf(admin, mock_state):
    assert admin.post(START).status_code == 403
    assert mock_state.enrollments == []
