"""Etiquetas y textos de la UI. ÚNICO lugar donde se traducen valores de la API.

Las plantillas reciben "vistas" ya armadas (diccionarios con textos y clases):
ningún valor crudo de la API se compara ni se traduce en una plantilla.
"""

from app import timefmt


EMPTY = "—"
NO_DATA = "Sin datos"
UNKNOWN_USER = "Desconocido"

OPERATOR_ROLES = {"admin": "Administrador", "viewer": "Consulta"}

RUNTIME_METHODS = {"both": "Biometría + RFID", "face": "Biometría", "rfid": "RFID"}
DOOR_MODES = {"simulate": "Simulación", "gpio": "GPIO (puerta real)"}
RUNTIME_OFFLINE_NOTES = {
    "running": "El runtime figura en ejecución, pero el heartbeat está vencido.",
    "stopped": "El runtime está detenido.",
    "unknown": "El runtime nunca informó su estado.",
}

# Valores que el front le manda a la API en el filtro `method`.
ACCESS_METHODS = {"RFID": "RFID", "facial": "Biometría"}

GRANTED = "AUTORIZADO"
DENIED = "NO AUTORIZADO"

# door_status → (etiqueta, clase). "simulated" nunca se muestra como "Abierta".
DOOR_STATUS = {
    "opened": ("Abierta", "ok"),
    "simulated": ("Simulada — sin apertura física", "warn"),
    "not_requested": ("Sin apertura", "muted"),
    "error": ("Error de puerta", "bad"),
}
DOOR_ERROR = "error"

# La API manda las alertas como texto: se mapean a códigos internos sólo acá.
CONSECUTIVE_FAILURES = "CONSECUTIVE_FAILURES"
RESTRICTED_TIME = "RESTRICTED_TIME"
OTHER = "OTHER"
ALERT_TEXTS = {
    "Tres intentos de ingreso fallidos consecutivos": CONSECUTIVE_FAILURES,
    "Intento de ingreso fuera de horario": RESTRICTED_TIME,
}
ALERT_LABELS = {
    CONSECUTIVE_FAILURES: "Rechazos consecutivos",
    RESTRICTED_TIME: "Fuera de horario",
}
DOOR_ERROR_ALERT = "Error de puerta"

ENROLLMENT_FINAL = {
    "completed": ("ok", "Tarjeta asociada a {name}"),
    "failed": ("error", "No se pudo asociar la tarjeta. Puede que ya pertenezca a otro usuario."),
    "expired": ("warn", "No se detectó ninguna tarjeta a tiempo."),
    "cancelled": ("warn", "Solicitud cancelada."),
}
ENROLLMENT_PENDING = "pending"
ENROLLMENT_COMPLETED = "completed"
ENROLLMENT_WAITING = "Acercá la tarjeta al lector"
READER_INACTIVE = "El lector RFID no está activo; la solicitud va a expirar"
ACTIVATE_FIRST = "Activá el usuario primero"
REVOKE_FIRST = "Revocá la tarjeta actual primero"
FACE_ENROLLMENT_INFO = "El registro facial se realiza en el puesto de enrolamiento local"

API_STALE = "desactualizado"
SIMULATION_BANNER = "Puerta en modo simulación: los accesos autorizados no abren la puerta física."


def operator_role(role):
    return OPERATOR_ROLES.get(role, role)


def text_or_empty(value):
    return value if value else EMPTY


# --- Runtime ----------------------------------------------------------------

def runtime_view(runtime, tz, now=None):
    online = bool(runtime.get("online"))
    methods = runtime.get("methods")
    door_mode = runtime.get("door_mode")
    updated_at = runtime.get("updated_at")
    return {
        "online": online,
        "online_label": "ONLINE" if online else "OFFLINE",
        "online_class": "ok" if online else "bad",
        "offline_note": None if online else RUNTIME_OFFLINE_NOTES.get(
            runtime.get("status"), str(runtime.get("status"))
        ),
        "heartbeat": timefmt.format_local(updated_at, tz) if updated_at else NO_DATA,
        "heartbeat_ago": timefmt.ago(updated_at, now) if updated_at else None,
        "methods_label": RUNTIME_METHODS.get(methods, methods or NO_DATA),
        "door_mode_label": DOOR_MODES.get(door_mode, door_mode or NO_DATA),
        "simulate": door_mode == "simulate",
        # El lector RFID atiende si el runtime está online y no es sólo facial.
        "rfid_reader_active": online and methods in ("both", "rfid"),
    }


# --- Usuarios ---------------------------------------------------------------

def full_name(user):
    parts = [user.get("first_name"), user.get("last_name")] if user else []
    return " ".join(part for part in parts if part) or None


def user_label(external_id, users):
    """"Nombre Apellido (user_005)", el ID solo si no hay nombre, o "Desconocido"."""
    if external_id is None:
        return UNKNOWN_USER
    name = full_name(users.get(external_id))
    return f"{name} ({external_id})" if name else external_id


def yes_no(value):
    return "Sí" if value else "No"


def user_view(user, tz):
    templates = user.get("biometric_templates", 0)
    return {
        "external_id": user["external_id"],
        "first_name": text_or_empty(user.get("first_name")),
        "last_name": text_or_empty(user.get("last_name")),
        "role": text_or_empty(user.get("role")),
        "raw": {name: user.get(name) or "" for name in ("first_name", "last_name", "role")},
        "name": full_name(user) or user["external_id"],
        "label": user_label(user["external_id"], {user["external_id"]: user}),
        "active": bool(user.get("active")),
        "active_label": "Activo" if user.get("active") else "Inactivo",
        "active_class": "ok" if user.get("active") else "bad",
        "has_face": bool(user.get("has_face")),
        "face_label": f"Sí ({templates})" if user.get("has_face") else "No",
        "templates": templates,
        "has_rfid": bool(user.get("has_rfid")),
        "rfid_label": yes_no(user.get("has_rfid")),
        "created_at": timefmt.format_local(user.get("created_at"), tz),
    }


# --- Eventos y alertas ------------------------------------------------------

def alert_code(text):
    return ALERT_TEXTS.get(text, OTHER)


def event_alert_codes(event):
    codes = {alert_code(text) for text in event.get("alert_reasons", ())}
    if event.get("restricted_time"):
        codes.add(RESTRICTED_TIME)
    return codes


def event_alerts(event):
    """Alertas del evento como [{code, label}].

    `restricted_time` marca "Fuera de horario" aunque el texto no venga: la
    alerta tiene cooldown en el runtime y no se repite.
    """
    alerts, seen = [], set()
    for text in event.get("alert_reasons", ()):
        code = alert_code(text)
        if code == OTHER:
            alerts.append({"code": OTHER, "label": text})
        elif code not in seen:
            seen.add(code)
            alerts.append({"code": code, "label": ALERT_LABELS[code]})
    if event.get("restricted_time") and RESTRICTED_TIME not in seen:
        alerts.append({"code": RESTRICTED_TIME, "label": ALERT_LABELS[RESTRICTED_TIME]})
    return alerts


def method_label(method):
    return ACCESS_METHODS.get(method, method)


def door_label(door_status):
    return DOOR_STATUS.get(door_status, (door_status, "muted"))[0]


def event_view(event, users, tz):
    granted = bool(event.get("granted"))
    door, door_class = DOOR_STATUS.get(event.get("door_status"), (event.get("door_status"), "muted"))
    external_id = event.get("external_id")
    return {
        "event_id": event["event_id"],
        "when": timefmt.format_local(event.get("occurred_at"), tz),
        "day": timefmt.api_day(event.get("occurred_at")),
        "external_id": external_id,
        "user_label": user_label(external_id, users),
        "method_label": method_label(event.get("method")),
        "granted": granted,
        "result_label": GRANTED if granted else DENIED,
        "result_class": "ok" if granted else "bad",
        "restricted": bool(event.get("restricted_time")),
        "restricted_label": yes_no(event.get("restricted_time")),
        "door_label": door,
        "door_class": door_class,
        "alerts": event_alerts(event),
    }


# --- Enrolamiento RFID ------------------------------------------------------

def enrollment_view(enrollment, user_name, now=None):
    status = enrollment.get("status")
    view = {
        "request_id": enrollment["request_id"],
        "external_id": enrollment["external_id"],
        "pending": status == ENROLLMENT_PENDING,
        "completed": status == ENROLLMENT_COMPLETED,
    }
    if view["pending"]:
        view["title"] = ENROLLMENT_WAITING
        view["remaining"] = timefmt.seconds_until(enrollment.get("expires_at"), now)
        return view
    kind, message = ENROLLMENT_FINAL.get(status, ("error", f"Estado desconocido: {status}"))
    error_code = enrollment.get("error_code")
    if status == "failed" and error_code != "card_unavailable":
        message = f"No se pudo asociar la tarjeta (código: {error_code or 'sin detalle'})."
    view["kind"] = kind
    view["message"] = message.format(name=user_name)
    return view
