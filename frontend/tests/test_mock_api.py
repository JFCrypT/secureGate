"""El mock tiene que comportarse como la API real (contrato §4 y PEDIDOS D1–D8)."""

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_TOKEN


AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def api(mock_api):
    return TestClient(mock_api, headers=AUTH)


def test_no_importa_nada_del_backend():
    source = (Path(__file__).parent.parent / "dev" / "mock_api.py").read_text(encoding="utf-8")
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])
    assert not modules & {"securegate", "raspberry", "app"}


def test_health_es_publico_y_el_resto_pide_token(mock_api):
    anonymous = TestClient(mock_api)
    assert anonymous.get("/health").json() == {
        "status": "ok", "database": "ok", "hardware": "runtime-separado",
    }
    response = anonymous.get("/api/v1/users")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_status_y_heartbeat(api, mock_state):
    runtime = api.get("/api/v1/status").json()["runtime"]
    assert runtime["online"] is True and runtime["methods"] == "both"
    assert runtime["updated_at"].endswith("+00:00")
    api.get("/mock/control?offline=1")
    runtime = api.get("/api/v1/status").json()["runtime"]
    assert runtime["online"] is False and runtime["status"] == "running"
    api.get("/mock/control?offline=unknown")
    assert api.get("/api/v1/status").json()["runtime"] == {
        "online": False, "status": "unknown", "methods": None,
        "door_mode": None, "updated_at": None,
    }


def test_usuarios_de_ejemplo_cubren_las_combinaciones(api):
    users = api.get("/api/v1/users").json()
    assert len(users) == 6
    assert any(not u["active"] for u in users)
    assert any(u["first_name"] is None for u in users)
    assert any(u["has_face"] and u["has_rfid"] for u in users)
    assert any(not u["has_face"] and not u["has_rfid"] for u in users)
    assert all("uid" not in key.lower() for u in users for key in u)


def test_validaciones_de_usuario(api):
    assert api.post("/api/v1/users", json={"external_id": "user_001"}).status_code == 409
    assert api.post("/api/v1/users", json={"external_id": "ana"}).status_code == 422
    extra = api.post("/api/v1/users", json={"external_id": "user_010", "uid": "x"})
    assert extra.status_code == 422 and isinstance(extra.json()["detail"], list)
    assert api.get("/api/v1/users/user_999").status_code == 404
    assert api.get("/api/v1/users/mal").status_code == 404
    assert api.patch("/api/v1/users/mal", json={"active": True}).status_code == 422
    empty = api.patch("/api/v1/users/user_001", json={})
    assert empty.status_code == 422 and empty.json()["detail"] == "Enviar al menos un campo."
    cleared = api.patch("/api/v1/users/user_001", json={"role": None})
    assert cleared.status_code == 200 and cleared.json()["role"] is None
    assert api.patch("/api/v1/users/user_001", json={"role": ""}).status_code == 422


def test_revocaciones(api):
    assert api.delete("/api/v1/users/user_001/rfid").json()["has_rfid"] is False
    again = api.delete("/api/v1/users/user_001/rfid")
    assert again.status_code == 404
    assert again.json()["detail"] == "El usuario no posee una tarjeta activa."
    face = api.delete("/api/v1/users/user_001/face").json()
    assert face["has_face"] is False and face["biometric_templates"] == 0
    assert api.delete("/api/v1/users/user_001/face").status_code == 404


def test_enrolamiento_completa_a_los_5_s(api, clock):
    created = api.post("/api/v1/users/user_002/rfid-enrollments", json={"timeout_seconds": 60})
    assert created.status_code == 201
    request = created.json()
    assert request["status"] == "pending" and request["external_id"] == "user_002"
    busy = api.post("/api/v1/users/user_006/rfid-enrollments", json={})
    assert busy.status_code == 409
    assert busy.json()["detail"] == "Ya existe otra solicitud de enrolamiento pendiente."
    clock.advance(6)
    done = api.get(f"/api/v1/rfid-enrollments/{request['request_id']}").json()
    assert done["status"] == "completed" and done["finished_at"]
    assert api.get("/api/v1/users/user_002").json()["has_rfid"] is True


def test_enrolamiento_conflictos_y_validacion(api):
    inactive = api.post("/api/v1/users/user_004/rfid-enrollments", json={})
    assert (inactive.status_code, inactive.json()["detail"]) == (409, "El usuario está deshabilitado.")
    has_card = api.post("/api/v1/users/user_001/rfid-enrollments", json={})
    assert has_card.status_code == 409 and "revocarla primero" in has_card.json()["detail"]
    assert api.post("/api/v1/users/user_999/rfid-enrollments", json={}).status_code == 404
    assert api.post("/api/v1/users/user_002/rfid-enrollments", json={"timeout_seconds": 5}).status_code == 422
    assert api.get("/api/v1/rfid-enrollments/99").status_code == 404


def test_enrolamiento_falla_expira_y_se_cancela(api, clock):
    api.get("/mock/control?enroll=failed")
    request_id = api.post("/api/v1/users/user_002/rfid-enrollments", json={}).json()["request_id"]
    clock.advance(6)
    failed = api.get(f"/api/v1/rfid-enrollments/{request_id}").json()
    assert (failed["status"], failed["error_code"]) == ("failed", "card_unavailable")

    api.get("/mock/control?enroll=expired")
    request_id = api.post("/api/v1/users/user_002/rfid-enrollments", json={"timeout_seconds": 10}).json()["request_id"]
    clock.advance(11)
    assert api.get(f"/api/v1/rfid-enrollments/{request_id}").json()["status"] == "expired"

    request_id = api.post("/api/v1/users/user_002/rfid-enrollments", json={}).json()["request_id"]
    assert api.delete(f"/api/v1/rfid-enrollments/{request_id}").json()["status"] == "cancelled"
    again = api.delete(f"/api/v1/rfid-enrollments/{request_id}")
    assert (again.status_code, again.json()["detail"]) == (404, "La solicitud no está pendiente.")


def test_eventos_filtros_y_resumen(api, mock_state):
    events = api.get("/api/v1/access-events?limit=500").json()
    assert len(events) == 80
    ids = [event["event_id"] for event in events]
    assert ids == sorted(ids, reverse=True)
    assert {event["door_status"] for event in events} == {"opened", "simulated", "not_requested", "error"}
    assert any(event["external_id"] is None for event in events)
    assert any(event["restricted_time"] and not event["alert_reasons"] for event in events)
    assert any("Tres intentos de ingreso fallidos consecutivos" in e["alert_reasons"] for e in events)
    assert all(event["occurred_at"].endswith("-03:00") for event in events)

    day = events[0]["occurred_at"][:10]
    of_day = api.get(f"/api/v1/access-events?limit=500&day={day}").json()
    assert of_day and all(event["occurred_at"].startswith(day) for event in of_day)
    summary = api.get(f"/api/v1/access-events/summary?day={day}").json()
    assert summary["total"] == len(of_day)
    assert summary["granted"] + summary["denied"] == summary["total"]

    rfid_denied = api.get("/api/v1/access-events?limit=500&method=RFID&granted=false").json()
    assert all(e["method"] == "RFID" and not e["granted"] for e in rfid_denied)
    assert api.get("/api/v1/access-events?limit=2&offset=1").json()[0]["event_id"] == ids[1]
    assert api.get("/api/v1/access-events?limit=501").status_code == 422
    assert api.get("/api/v1/access-events?day=ayer").status_code == 422


def test_base_caida(api):
    api.get("/mock/control?db_down=true")
    assert api.get("/health").status_code == 503
    response = api.get("/api/v1/users")
    assert response.status_code == 500 and response.text == "Internal Server Error"
