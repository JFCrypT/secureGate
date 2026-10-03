import asyncio
import logging

import httpx
import pytest
import respx

from app.api_client import (
    ApiBackendError,
    ApiConfigError,
    ApiConflict,
    ApiNotFound,
    ApiUnavailable,
    ApiValidation,
    SecureGateClient,
)
from tests.conftest import API_URL, TEST_TOKEN


def run(coroutine):
    return asyncio.run(coroutine)


@pytest.fixture
def client():
    return SecureGateClient(API_URL, TEST_TOKEN)


USER = {
    "external_id": "user_005", "first_name": "Ana", "last_name": "Pérez", "role": "docente",
    "active": True, "created_at": "2026-10-02 14:00:00",
    "has_face": False, "biometric_templates": 0, "has_rfid": False,
}


@respx.mock
def test_manda_el_bearer_y_devuelve_el_json(client):
    route = respx.get(f"{API_URL}/api/v1/status").respond(json={"api": "ok"})
    assert run(client.status()) == {"api": "ok"}
    assert route.calls.last.request.headers["authorization"] == f"Bearer {TEST_TOKEN}"


@respx.mock
@pytest.mark.parametrize("error", [httpx.ConnectError("x"), httpx.ReadTimeout("x")])
def test_api_caida_o_timeout(client, error):
    respx.get(f"{API_URL}/api/v1/status").mock(side_effect=error)
    with pytest.raises(ApiUnavailable) as raised:
        run(client.status())
    assert raised.value.message == "API no disponible"


@respx.mock
def test_401_es_error_de_configuracion_y_no_loguea_el_token(client, caplog):
    respx.get(f"{API_URL}/api/v1/users").respond(
        401, json={"detail": "Token de API inválido o ausente."}
    )
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ApiConfigError) as raised:
            run(client.list_users())
    assert raised.value.message == "Error de configuración del servidor"
    assert "401" in caplog.text
    assert TEST_TOKEN not in caplog.text


@respx.mock
def test_404_con_detail(client):
    respx.get(f"{API_URL}/api/v1/users/user_999").respond(404, json={"detail": "Usuario inexistente."})
    with pytest.raises(ApiNotFound) as raised:
        run(client.get_user("user_999"))
    assert raised.value.message == "Usuario inexistente."


@respx.mock
def test_id_mal_formado_no_llega_a_la_api(client):
    with pytest.raises(ApiNotFound):
        run(client.get_user("../status"))
    with pytest.raises(ApiNotFound):
        run(client.update_user("otro", {"active": True}))
    assert not respx.calls


@respx.mock
def test_409_muestra_el_detail_de_la_api(client):
    respx.post(f"{API_URL}/api/v1/users/user_005/rfid-enrollments").respond(
        409, json={"detail": "Ya existe otra solicitud de enrolamiento pendiente."}
    )
    with pytest.raises(ApiConflict) as raised:
        run(client.create_enrollment("user_005"))
    assert raised.value.message == "Ya existe otra solicitud de enrolamiento pendiente."


@respx.mock
def test_422_con_lista_da_errores_por_campo(client):
    respx.post(f"{API_URL}/api/v1/users").respond(422, json={"detail": [
        {"loc": ["body", "first_name"], "msg": "String should have at most 100 characters"},
        {"loc": ["body"], "msg": "Extra inputs are not permitted"},
    ]})
    with pytest.raises(ApiValidation) as raised:
        run(client.create_user("user_007", first_name="x" * 101))
    assert raised.value.fields == {"first_name": "String should have at most 100 characters"}
    assert raised.value.errors == ["Extra inputs are not permitted"]


@respx.mock
def test_422_con_texto(client):
    respx.patch(f"{API_URL}/api/v1/users/user_005").respond(422, json={"detail": "Enviar al menos un campo."})
    with pytest.raises(ApiValidation) as raised:
        run(client.update_user("user_005", {}))
    assert raised.value.errors == ["Enviar al menos un campo."]


@respx.mock
@pytest.mark.parametrize("code", [500, 503])
def test_500_y_503_son_base_no_disponible(client, code):
    # La API real devuelve 500 en texto plano si falla SQLite en /api/v1/*.
    respx.get(f"{API_URL}/api/v1/status").respond(code, text="Internal Server Error")
    with pytest.raises(ApiBackendError) as raised:
        run(client.status())
    assert raised.value.message == "Base de datos no disponible"


def test_active_nulo_nunca_se_manda(client):
    with pytest.raises(ValueError):
        run(client.update_user("user_005", {"active": None}))


@respx.mock
def test_lista_de_usuarios_se_cachea_y_se_invalida(client):
    route = respx.get(f"{API_URL}/api/v1/users").respond(json=[USER])
    respx.patch(f"{API_URL}/api/v1/users/user_005").respond(json=USER)
    run(client.list_users())
    run(client.list_users())
    assert route.call_count == 1
    run(client.update_user("user_005", {"role": "docente"}))
    assert run(client.users_by_id()) == {"user_005": USER}
    assert route.call_count == 2


@respx.mock
def test_cache_de_usuarios_vence_a_los_10_s():
    now = [100.0]
    client = SecureGateClient(API_URL, TEST_TOKEN, clock=lambda: now[0])
    route = respx.get(f"{API_URL}/api/v1/users").respond(json=[])
    run(client.list_users())
    now[0] += 9
    run(client.list_users())
    assert route.call_count == 1
    now[0] += 2
    run(client.list_users())
    assert route.call_count == 2


@respx.mock
def test_filtros_de_eventos(client):
    route = respx.get(f"{API_URL}/api/v1/access-events").respond(json=[])
    run(client.list_events(limit=50, offset=100, day="2026-10-02", method="RFID", granted=False))
    assert dict(route.calls.last.request.url.params) == {
        "limit": "50", "offset": "100", "day": "2026-10-02", "method": "RFID", "granted": "false",
    }


@respx.mock
def test_eventos_por_dia_pagina_hasta_agotar_y_respeta_el_tope(client):
    def page(request):
        offset = int(request.url.params["offset"])
        size = 500 if offset == 0 else 20
        return httpx.Response(200, json=[{"event_id": offset + i} for i in range(size)])

    respx.get(f"{API_URL}/api/v1/access-events").mock(side_effect=page)
    events, truncated = run(client.events_for_days(["2026-10-01", "2026-10-02"], cap=20000))
    assert len(events) == 1040 and not truncated
    events, truncated = run(client.events_for_days(["2026-10-01", "2026-10-02"], cap=600))
    assert len(events) == 600 and truncated


# --- Contra el mock (mismos códigos y textos que la API real) ---------------

def test_contra_el_mock(api_transport):
    client = SecureGateClient(API_URL, TEST_TOKEN, transport=api_transport)
    status = run(client.status())
    assert status["runtime"]["online"] is True
    assert status["users"]["total"] == 6
    created = run(client.create_user("user_007", first_name="Zoe"))
    assert created["first_name"] == "Zoe" and created["has_rfid"] is False
    with pytest.raises(ApiConflict) as raised:
        run(client.create_user("user_007"))
    assert raised.value.message == "El usuario ya existe."
    with pytest.raises(ApiValidation) as raised:
        run(client.create_user("user_008", first_name=""))
    assert "first_name" in raised.value.fields


def test_token_incorrecto_contra_el_mock(api_transport):
    client = SecureGateClient(API_URL, "otro-token-" + "z" * 32, transport=api_transport)
    with pytest.raises(ApiConfigError):
        run(client.status())


def test_base_caida_contra_el_mock(api_transport, mock_state):
    mock_state.db_down = True
    client = SecureGateClient(API_URL, TEST_TOKEN, transport=api_transport)
    with pytest.raises(ApiBackendError):
        run(client.list_users())
    with pytest.raises(ApiBackendError):
        run(client.health())
