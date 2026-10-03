import re

import httpx
import pytest

from tests.conftest import api_responds


def rows(text):
    return [int(n) for n in re.findall(r'<tr id="evento-(\d+)"', text)]


def test_primera_pagina(viewer, mock_state):
    page = viewer.get("/dashboard/historial")
    assert page.status_code == 200
    ids = rows(page.text)
    assert ids == list(range(80, 30, -1))  # 50 más nuevos, en orden
    for column in ("Fecha y hora", "Usuario", "Método", "Resultado", "Fuera de horario", "Puerta", "Alertas"):
        assert f"<th>{column}</th>" in page.text
    assert "Siguiente" in page.text and "Anterior" not in page.text
    assert "página" not in page.text.lower().replace("esta página", "")  # sin "página X de Y"


def test_paginado_hasta_agotar(viewer):
    first = viewer.get("/dashboard/historial").text
    assert 'href="/dashboard/historial?offset=50"' in first
    second = viewer.get("/dashboard/historial?offset=50").text
    assert rows(second) == list(range(30, 0, -1))
    assert "Siguiente" not in second  # página incompleta: no hay más
    assert 'href="/dashboard/historial"' in second and "Anterior" in second


def test_filtros_que_van_a_la_api(viewer, mock_state, front):
    seen = {}
    original = front.state.api.list_events

    async def spy(**kwargs):
        seen.update(kwargs)
        return await original(**kwargs)

    front.state.api.list_events = spy
    day = mock_state.events[-1]["occurred_at"][:10]
    text = viewer.get(f"/dashboard/historial?dia={day}&metodo=RFID&resultado=rechazado").text
    assert seen == {"limit": 50, "offset": 0, "day": day, "method": "RFID", "granted": False}
    expected = [e["event_id"] for e in reversed(mock_state.events)
                if e["occurred_at"].startswith(day) and e["method"] == "RFID" and not e["granted"]]
    assert rows(text) == expected[:50]
    assert "NO AUTORIZADO" in text or not expected


@pytest.mark.parametrize("query,keep", [
    ("usuario=user_001", lambda e: e["external_id"] == "user_001"),
    ("usuario=desconocido", lambda e: e["external_id"] is None),
    ("fuera_horario=1", lambda e: e["restricted_time"]),
    ("con_alertas=1", lambda e: bool(e["alert_reasons"])),
    ("error_puerta=1", lambda e: e["door_status"] == "error"),
    ("usuario=user_001&fuera_horario=1", lambda e: e["external_id"] == "user_001" and e["restricted_time"]),
])
def test_filtros_del_bff_sobre_la_pagina(viewer, mock_state, query, keep):
    text = viewer.get(f"/dashboard/historial?{query}").text
    page = list(reversed(mock_state.events))[:50]
    assert rows(text) == [e["event_id"] for e in page if keep(e)]
    assert "de los 50 de esta página" in text
    # "Siguiente" depende de la página cruda y conserva los filtros.
    assert f'href="/dashboard/historial?{query.replace("&", "&amp;")}&amp;offset=50"' in text


def test_filtros_invalidos_se_ignoran(viewer):
    page = viewer.get("/dashboard/historial?dia=ayer&metodo=PIN&resultado=x&usuario=user_999&offset=-5")
    assert page.status_code == 200
    assert len(rows(page.text)) == 50
    assert "La fecha no es válida" in page.text


def test_sin_resultados(viewer):
    text = viewer.get("/dashboard/historial?dia=2020-01-01").text
    assert "No hay registros para ese filtro." in text and "Siguiente" not in text


def test_etiquetas_en_la_tabla(viewer, mock_state):
    text = viewer.get("/dashboard/historial").text
    assert "Simulada — sin apertura física" in text
    assert "Desconocido" in text and "Ana Pérez (user_001)" in text
    assert "<td>Biometría</td>" in text and "<td>facial</td>" not in text
    assert "Tres intentos" not in text and "Rechazos consecutivos" in viewer.get("/dashboard/historial?con_alertas=1").text


def test_enlace_a_un_evento(viewer, mock_state):
    event = mock_state.events[10]
    day = event["occurred_at"][:10]
    page = viewer.get(f"/dashboard/historial?dia={day}&evento={event['event_id']}")
    assert page.status_code == 200
    assert rows(page.text) == [event["event_id"]]
    assert 'class="destacado"' in page.text
    assert f'href="/dashboard/historial?dia={day}"' in page.text


def test_evento_inexistente(viewer):
    page = viewer.get("/dashboard/historial?dia=2026-10-03&evento=99999")
    assert page.status_code == 404 and "No encontrado" in page.text


@pytest.mark.parametrize("error,code,text", [
    (httpx.ConnectError("x"), 503, "API no disponible"),
    (lambda request: httpx.Response(401, json={"detail": "x"}), 502, "Error de configuración del servidor"),
    (lambda request: httpx.Response(500, text="Internal Server Error"), 503, "Base de datos no disponible"),
])
def test_errores_de_la_api(viewer, front, error, code, text):
    with api_responds(front, error):
        page = viewer.get("/dashboard/historial")
    assert page.status_code == code and text in page.text
    assert viewer.get("/dashboard/historial").status_code == 200  # se recupera y sigue logueado


def test_sin_sesion(client):
    assert client.get("/dashboard/historial").status_code == 303
