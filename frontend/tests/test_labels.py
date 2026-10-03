from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app import labels, timefmt


TZ = ZoneInfo("America/Argentina/Buenos_Aires")
USERS = {
    "user_005": {"external_id": "user_005", "first_name": "Ana", "last_name": "Pérez"},
    "user_006": {"external_id": "user_006", "first_name": None, "last_name": None},
}


def event(**overrides):
    data = {
        "event_id": 12, "occurred_at": "2026-10-02T22:15:00-03:00", "method": "RFID",
        "external_id": "user_005", "granted": True, "restricted_time": False,
        "alert_reasons": [], "door_status": "opened",
    }
    data.update(overrides)
    return data


def test_fechas():
    assert timefmt.format_local("2026-10-03T17:00:05+00:00", TZ) == "03/10/2026 14:00:05"
    assert timefmt.format_local("2026-10-02T22:15:00-03:00", TZ) == "02/10/2026 22:15:00"
    # created_at de usuarios viene sin zona: se asume UTC.
    assert timefmt.format_local("2026-10-02 14:00:00", TZ) == "02/10/2026 11:00:00"
    assert timefmt.format_local(None, TZ) == "—"
    assert timefmt.format_local("no es fecha", TZ) == "—"
    assert timefmt.api_day("2026-10-02T22:15:00-03:00") == "2026-10-02"


def test_hace_n():
    now = datetime(2026, 10, 3, 17, 0, 12, tzinfo=timezone.utc)
    assert timefmt.ago("2026-10-03T17:00:05+00:00", now) == "hace 7 s"
    assert timefmt.ago("2026-10-03T16:50:00+00:00", now) == "hace 10 min"
    assert timefmt.ago("2026-10-03T12:00:00+00:00", now) == "hace 5 h"
    assert timefmt.ago("2026-10-03T17:00:30+00:00", now) == "hace 0 s"
    assert timefmt.ago(None, now) is None
    assert timefmt.seconds_until("2026-10-03T17:01:00+00:00", now) == 48
    assert timefmt.seconds_until("2026-10-03T16:00:00+00:00", now) == 0


def test_runtime_online():
    view = labels.runtime_view({
        "online": True, "status": "running", "methods": "both",
        "door_mode": "simulate", "updated_at": "2026-10-03T17:00:05+00:00",
    }, TZ, datetime(2026, 10, 3, 17, 0, 9, tzinfo=timezone.utc))
    assert view["online_label"] == "ONLINE" and view["online_class"] == "ok"
    assert view["offline_note"] is None
    assert view["methods_label"] == "Biometría + RFID"
    assert view["door_mode_label"] == "Simulación" and view["simulate"] is True
    assert view["heartbeat"] == "03/10/2026 14:00:05" and view["heartbeat_ago"] == "hace 4 s"
    assert view["rfid_reader_active"] is True


def test_runtime_offline_y_sin_datos():
    view = labels.runtime_view({
        "online": False, "status": "unknown", "methods": None,
        "door_mode": None, "updated_at": None,
    }, TZ)
    assert view["online_label"] == "OFFLINE" and view["online_class"] == "bad"
    assert view["methods_label"] == "Sin datos" and view["door_mode_label"] == "Sin datos"
    assert view["heartbeat"] == "Sin datos" and view["heartbeat_ago"] is None
    assert view["simulate"] is False and view["rfid_reader_active"] is False
    stale = labels.runtime_view({
        "online": False, "status": "running", "methods": "face",
        "door_mode": "gpio", "updated_at": "2026-10-03T17:00:05+00:00",
    }, TZ)
    assert "heartbeat está vencido" in stale["offline_note"]
    assert stale["methods_label"] == "Biometría"
    assert stale["door_mode_label"] == "GPIO (puerta real)"


def test_puerta_simulada_nunca_es_abierta():
    assert labels.door_label("simulated") == "Simulada — sin apertura física"
    assert labels.door_label("opened") == "Abierta"
    assert labels.door_label("not_requested") == "Sin apertura"
    assert labels.door_label("error") == "Error de puerta"
    view = labels.event_view(event(door_status="simulated"), USERS, TZ)
    assert "Abierta" not in view["door_label"] and view["door_class"] == "warn"


def test_evento_autorizado():
    view = labels.event_view(event(), USERS, TZ)
    assert view["user_label"] == "Ana Pérez (user_005)"
    assert view["result_label"] == "AUTORIZADO" and view["result_class"] == "ok"
    assert view["method_label"] == "RFID"
    assert view["when"] == "02/10/2026 22:15:00" and view["day"] == "2026-10-02"
    assert view["alerts"] == []


def test_evento_desconocido_y_metodos():
    view = labels.event_view(
        event(external_id=None, granted=False, method="facial", door_status="not_requested"),
        USERS, TZ,
    )
    assert view["user_label"] == "Desconocido"
    assert view["result_label"] == "NO AUTORIZADO" and view["result_class"] == "bad"
    assert view["method_label"] == "Biometría"
    assert labels.method_label("PIN") == "PIN"
    assert labels.user_label("user_006", USERS) == "user_006"
    assert labels.user_label("user_999", USERS) == "user_999"


def test_mapeo_de_alertas():
    view = labels.event_view(event(alert_reasons=[
        "Tres intentos de ingreso fallidos consecutivos",
        "Intento de ingreso fuera de horario",
        "Algo nuevo del backend",
    ], restricted_time=True), USERS, TZ)
    assert view["alerts"] == [
        {"code": "CONSECUTIVE_FAILURES", "label": "Rechazos consecutivos"},
        {"code": "RESTRICTED_TIME", "label": "Fuera de horario"},
        {"code": "OTHER", "label": "Algo nuevo del backend"},
    ]


def test_fuera_de_horario_sin_texto_de_alerta():
    # La alerta tiene cooldown: restricted_time marca el evento igual.
    view = labels.event_view(event(restricted_time=True), USERS, TZ)
    assert view["alerts"] == [{"code": "RESTRICTED_TIME", "label": "Fuera de horario"}]
    assert labels.event_alert_codes(event(restricted_time=True)) == {"RESTRICTED_TIME"}


def test_usuario_sin_nombre_ni_rol():
    view = labels.user_view({
        "external_id": "user_005", "first_name": None, "last_name": None, "role": None,
        "active": True, "created_at": "2026-10-02 14:00:00",
        "has_face": True, "biometric_templates": 2, "has_rfid": False,
    }, TZ)
    assert view["first_name"] == "—" and view["role"] == "—"
    assert view["name"] == "user_005"
    assert view["face_label"] == "Sí (2)" and view["rfid_label"] == "No"
    assert view["created_at"] == "02/10/2026 11:00:00"
