from datetime import datetime, timedelta, timezone
import re

import httpx
import pytest

from app import timefmt
from tests.conftest import api_responds


FAILURES = "Tres intentos de ingreso fallidos consecutivos"
NOW = datetime(2026, 10, 3, 18, 0, 0, tzinfo=timezone.utc)  # 15:00 en Buenos Aires


def event(event_id, hours_ago, **overrides):
    moment = (NOW - timedelta(hours=hours_ago)).astimezone(timezone(timedelta(hours=-3)))
    data = {
        "event_id": event_id, "occurred_at": moment.isoformat(timespec="seconds"), "method": "RFID",
        "external_id": "user_001", "granted": True, "restricted_time": False,
        "alert_reasons": [], "door_status": "simulated",
    }
    data.update(overrides)
    return data


@pytest.fixture
def scenario(mock_state, monkeypatch):
    monkeypatch.setattr(timefmt, "now_utc", lambda: NOW)
    mock_state.events[:] = [
        event(1, 150, door_status="error"),                                   # fuera de 7 d... no: 6,25 d
        event(2, 200, door_status="error"),                                   # más de 7 días: nunca cuenta
        event(3, 30, granted=False, alert_reasons=[FAILURES], door_status="not_requested"),
        event(4, 23, door_status="error"),
        event(5, 5, granted=False, external_id=None, alert_reasons=[FAILURES],
              restricted_time=True, door_status="not_requested"),
        event(6, 2, restricted_time=True),                                    # sin texto: cuenta igual
        event(7, 1),                                                          # normal
    ]
    return mock_state


def counts(text):
    return dict(re.findall(r"<dt>([^<]+)</dt><dd[^>]*>(\d+)</dd>", text))


def test_24_horas_por_defecto(viewer, scenario):
    page = viewer.get("/dashboard/alertas")
    assert page.status_code == 200
    assert counts(page.text) == {
        "Error de puerta": "1", "Rechazos consecutivos": "1", "Intentos fuera de horario": "2",
    }
    assert "Últimas 24 h" in page.text
    assert page.text.count("Ver evento") == 4


def test_7_dias(viewer, scenario):
    text = viewer.get("/dashboard/alertas?periodo=7d").text
    assert counts(text) == {
        "Error de puerta": "2", "Rechazos consecutivos": "2", "Intentos fuera de horario": "2",
    }
    assert "evento=2" not in text  # más viejo que el período


def test_periodo_invalido_usa_24_h(viewer, scenario):
    assert "Últimas 24 h" in viewer.get("/dashboard/alertas?periodo=1y").text


def test_cada_alerta_enlaza_al_evento_en_el_historial(viewer, scenario):
    text = viewer.get("/dashboard/alertas").text
    links = re.findall(r'href="(/dashboard/historial\?dia=[^"]+evento=\d+)"', text)
    assert len(links) == 4
    target = viewer.get(links[0].replace("&amp;", "&"))
    assert target.status_code == 200 and 'class="destacado"' in target.text


def test_estado_actual(viewer, scenario):
    text = viewer.get("/dashboard/alertas").text
    assert "modo simulación" in text and "Runtime OFFLINE" not in text
    scenario.offline = "stopped"
    scenario.door_mode = "gpio"
    text = viewer.get("/dashboard/alertas").text
    assert "Runtime OFFLINE" in text and "El runtime está detenido." in text
    assert "modo simulación" not in text


def test_sin_alertas(viewer, scenario):
    scenario.events[:] = [event(1, 1)]
    scenario.door_mode = "gpio"
    text = viewer.get("/dashboard/alertas").text
    assert "Sin alertas en el período." in text and "sin avisos de estado" in text


def test_api_caida(viewer, front, scenario):
    with api_responds(front, httpx.ConnectError("x")):
        page = viewer.get("/dashboard/alertas")
    assert page.status_code == 200
    assert "API no disponible" in page.text and "no se pudieron calcular las alertas" in page.text


def test_resumen_en_el_dashboard(viewer, scenario, front):
    assert 'hx-get="/dashboard/partials/alertas-resumen"' in viewer.get("/dashboard/").text
    partial = viewer.get("/dashboard/partials/alertas-resumen")
    assert partial.status_code == 200
    assert counts(partial.text)["Intentos fuera de horario"] == "2"
    assert 'href="/dashboard/alertas"' in partial.text
    with api_responds(front, httpx.ConnectError("x")):
        assert "API no disponible" in viewer.get("/dashboard/partials/alertas-resumen").text


def test_sin_sesion(client):
    assert client.get("/dashboard/alertas").status_code == 303
