from datetime import date
from zoneinfo import ZoneInfo
import csv
import io
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app import reports
from tests.conftest import TEST_TOKEN, api_responds


TZ = ZoneInfo("America/Argentina/Buenos_Aires")
USERS = {"user_001": {"external_id": "user_001", "first_name": "Ana", "last_name": "Pérez", "role": "docente"}}


def event(event_id, day="2026-10-02", **overrides):
    data = {
        "event_id": event_id, "occurred_at": f"{day}T22:15:00-03:00", "method": "RFID",
        "external_id": "user_001", "granted": True, "restricted_time": False,
        "alert_reasons": [], "door_status": "simulated",
    }
    data.update(overrides)
    return data


# --- Rango ------------------------------------------------------------------

def test_rango_por_defecto_son_los_ultimos_7_dias():
    start, end, error = reports.parse_range("", "", date(2026, 10, 3))
    assert (start, end, error) == (date(2026, 9, 27), date(2026, 10, 3), None)
    assert len(reports.days_between(start, end)) == 7


@pytest.mark.parametrize("desde,hasta,fragment", [
    ("2026-10-03", "2026-10-01", "no puede ser posterior"),
    ("2026-09-01", "2026-10-02", "31 días"),
    ("ayer", "2026-10-02", "no son válidas"),
])
def test_rangos_invalidos(desde, hasta, fragment):
    assert fragment in reports.parse_range(desde, hasta, date(2026, 10, 3))[2]


def test_31_dias_exactos_es_valido():
    assert reports.parse_range("2026-09-02", "2026-10-02", date(2026, 10, 3))[2] is None


# --- Agregaciones -----------------------------------------------------------

def test_agregaciones():
    events = [
        event(1), event(2, method="facial"),
        event(3, granted=False, external_id=None, door_status="not_requested"),
        event(4, day="2026-10-01", granted=False),
    ]
    days = reports.days_between(date(2026, 9, 30), date(2026, 10, 2))
    report = reports.aggregate(events, USERS, days)
    assert report["totals"]["total"] == 4
    assert (report["totals"]["granted"], report["totals"]["granted_pct"]) == (2, 50.0)
    assert (report["totals"]["denied"], report["totals"]["denied_pct"]) == (2, 50.0)
    assert [(u["label"], u["granted"], u["denied"]) for u in report["by_user"]] == [
        ("Ana Pérez (user_001)", 2, 1), ("Desconocido", 0, 1),
    ]
    assert [(m["label"], m["total"]) for m in report["by_method"]] == [("RFID", 3), ("Biometría", 1)]
    assert [(d["day"], d["label"], d["total"]) for d in report["by_day"]] == [
        ("2026-09-30", "30/09", 0), ("2026-10-01", "01/10", 1), ("2026-10-02", "02/10", 3),
    ]


def test_sin_eventos_no_divide_por_cero():
    report = reports.aggregate([], {}, [date(2026, 10, 2)])
    assert report["totals"]["granted_pct"] == 0.0 and report["by_user"] == []
    assert reports.chart(report["by_day"])["bars"][0]["granted_h"] == 0


def test_geometria_del_grafico():
    days = reports.days_between(date(2026, 9, 3), date(2026, 10, 3))
    by_day = reports.aggregate([event(1), event(2, granted=False)], USERS, days)["by_day"]
    chart = reports.chart(by_day)
    assert len(chart["bars"]) == 31 and chart["peak"] == 2
    bar = chart["bars"][-2]  # 2026-10-02: 1 autorizado y 1 rechazado, apilados
    assert bar["granted_h"] == bar["denied_h"] == 70.0
    assert bar["denied_y"] == 0.0 and bar["granted_y"] == 70.0
    assert all(b["x"] + b["width"] <= chart["width"] for b in chart["bars"])
    assert sum(1 for b in chart["bars"] if b["label"]) <= 10


# --- CSV --------------------------------------------------------------------

def parse_csv(data):
    assert data.startswith(b"\xef\xbb\xbf")  # BOM para Excel
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))


def test_csv():
    rows = parse_csv(reports.build_csv([
        event(2, granted=False, external_id=None, method="facial", restricted_time=True,
              alert_reasons=["Tres intentos de ingreso fallidos consecutivos"], door_status="not_requested"),
        event(1),
    ], USERS, TZ))
    assert rows[0] == [
        "fecha_hora", "usuario_id", "nombre", "apellido", "rol", "metodo",
        "resultado", "fuera_de_horario", "estado_puerta", "alertas",
    ]
    assert rows[1] == [
        "02/10/2026 22:15:00", "user_001", "Ana", "Pérez", "docente", "RFID",
        "AUTORIZADO", "NO", "Simulada — sin apertura física", "",
    ]
    assert rows[2] == [
        "02/10/2026 22:15:00", "", "", "", "", "Biometría",
        "NO AUTORIZADO", "SI", "Sin apertura", "Rechazos consecutivos | Fuera de horario",
    ]


def test_csv_neutraliza_formulas():
    users = {"user_001": {"first_name": "=HYPERLINK(1)", "last_name": "+1", "role": "@x"}}
    row = parse_csv(reports.build_csv([event(1)], users, TZ))[1]
    assert row[2:5] == ["'=HYPERLINK(1)", "'+1", "'@x"]


# --- Pantalla y exportación -------------------------------------------------

def stats(text):
    return {k: int(v) for k, v in re.findall(r"<dt>([^<]+)</dt><dd[^>]*>(\d+)", text)}


def mock_range(mock_state):
    days = sorted({e["occurred_at"][:10] for e in mock_state.events})
    return days[-7], days[-1]


def test_reporte_cuadra_con_summary_por_dia(viewer, mock_api, mock_state):
    desde, hasta = mock_range(mock_state)
    page = viewer.get(f"/dashboard/reportes?desde={desde}&hasta={hasta}")
    assert page.status_code == 200
    api = TestClient(mock_api, headers={"Authorization": f"Bearer {TEST_TOKEN}"})
    days = reports.days_between(date.fromisoformat(desde), date.fromisoformat(hasta))
    summaries = [api.get(f"/api/v1/access-events/summary?day={d.isoformat()}").json() for d in days]
    found = stats(page.text)
    assert found["Total"] == sum(s["total"] for s in summaries)
    assert found["Autorizados"] == sum(s["granted"] for s in summaries)
    assert found["Rechazados"] == sum(s["denied"] for s in summaries)
    for day, summary in zip(days, summaries):
        row = re.search(rf"<td>{day.strftime('%d/%m')}</td><td>(\d+)</td><td>(\d+)</td><td>(\d+)</td>", page.text)
        assert [int(n) for n in row.groups()] == [summary["granted"], summary["denied"], summary["total"]]
    assert "<svg" in page.text and "Por usuario" in page.text and "Por método" in page.text
    assert "http" not in page.text.split("<svg")[1].split("</svg>")[0]  # sin recursos externos


def test_por_defecto_ultimos_7_dias(viewer):
    page = viewer.get("/dashboard/reportes")
    assert page.status_code == 200 and page.text.count("<rect class=\"bar-ok\"") == 7


def test_filtros_de_metodo_y_resultado(viewer, mock_state):
    desde, hasta = mock_range(mock_state)
    text = viewer.get(f"/dashboard/reportes?desde={desde}&hasta={hasta}&metodo=RFID&resultado=rechazado").text
    expected = [e for e in mock_state.events
                if desde <= e["occurred_at"][:10] <= hasta and e["method"] == "RFID" and not e["granted"]]
    assert stats(text)["Total"] == len(expected) and stats(text)["Autorizados"] == 0
    assert "metodo=RFID" in text and "resultado=rechazado" in text  # el CSV usa los mismos filtros


@pytest.mark.parametrize("query,message", [
    ("desde=2026-01-01&hasta=2026-03-01", "no puede superar los 31 días"),
    ("desde=2026-10-03&hasta=2026-10-01", "no puede ser posterior"),
    ("desde=x", "no son válidas"),
])
def test_rango_invalido_en_pantalla_y_csv(viewer, query, message):
    page = viewer.get(f"/dashboard/reportes?{query}")
    assert page.status_code == 422 and message in page.text and "<svg" not in page.text
    export = viewer.get(f"/dashboard/reportes/export.csv?{query}")
    assert export.status_code == 422 and message in export.text


def test_exportar_csv(viewer, mock_state):
    desde, hasta = mock_range(mock_state)
    response = viewer.get(f"/dashboard/reportes/export.csv?desde={desde}&hasta={hasta}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == f'attachment; filename="accesos_{desde}_{hasta}.csv"'
    rows = parse_csv(response.content)
    expected = [e for e in mock_state.events if desde <= e["occurred_at"][:10] <= hasta]
    assert len(rows) == len(expected) + 1
    assert any("Pérez" in row for row in rows)  # acentos
    assert "uid" not in response.text.lower() and TEST_TOKEN not in response.text
    assert all(row[6] in ("AUTORIZADO", "NO AUTORIZADO") for row in rows[1:])
    assert "Abierta" not in [row[8] for row in rows[1:] if row[8].startswith("Simulada")]


def test_tope_de_eventos_avisa(viewer, mock_state, monkeypatch):
    monkeypatch.setattr(reports, "MAX_EVENTS", 10)
    desde, hasta = mock_range(mock_state)
    page = viewer.get(f"/dashboard/reportes?desde={desde}&hasta={hasta}")
    assert "supera los 10 eventos" in page.text and stats(page.text)["Total"] == 10
    export = viewer.get(f"/dashboard/reportes/export.csv?desde={desde}&hasta={hasta}")
    assert export.headers["x-reporte-truncado"] == "10" and len(parse_csv(export.content)) == 11


def test_api_caida(viewer, front):
    with api_responds(front, httpx.ConnectError("x")):
        assert viewer.get("/dashboard/reportes").status_code == 503
        export = viewer.get("/dashboard/reportes/export.csv")
    assert export.status_code == 503 and "API no disponible" in export.text


def test_sin_sesion(client):
    assert client.get("/dashboard/reportes").status_code == 303
    assert client.get("/dashboard/reportes/export.csv").status_code == 303
