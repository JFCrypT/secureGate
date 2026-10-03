"""Etiquetas y textos de la UI. ÚNICO lugar donde se traducen valores de la API."""

EMPTY = "—"

OPERATOR_ROLES = {"admin": "Administrador", "viewer": "Consulta"}


def operator_role(role):
    return OPERATOR_ROLES.get(role, role)
