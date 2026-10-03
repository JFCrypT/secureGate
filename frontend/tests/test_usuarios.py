import httpx
import pytest

from app.routes.usuarios import next_external_id
from tests.conftest import api_responds, csrf_of


def post(client, path, **data):
    data["csrf_token"] = csrf_of(client)
    return client.post(path, data=data)


# --- Listado ----------------------------------------------------------------

def test_listado(viewer):
    page = viewer.get("/dashboard/usuarios")
    assert page.status_code == 200
    for text in ("Ana", "Pérez", "docente", "user_001", "user_006", "Sí (2)", "Inactivo"):
        assert text in page.text
    assert "Mostrando 6 de 6" in page.text
    assert "Nuevo usuario" not in page.text  # el viewer no ve acciones de escritura


def test_listado_admin_ve_el_alta(admin):
    assert "Nuevo usuario" in admin.get("/dashboard/usuarios").text


@pytest.mark.parametrize("query,expected", [
    ("q=pérez", {"user_001"}),
    ("q=user_00", {"user_001", "user_002", "user_003", "user_004", "user_005", "user_006"}),
    ("q=ana+pérez", {"user_001"}),
    ("activo=no", {"user_004"}),
    ("rostro=si", {"user_001", "user_002", "user_004"}),
    ("tarjeta=si&rostro=no", {"user_003"}),
    ("activo=si&tarjeta=no&rostro=no", {"user_005", "user_006"}),
    ("q=nadie", set()),
])
def test_busqueda_y_filtros(viewer, query, expected):
    text = viewer.get(f"/dashboard/usuarios?{query}").text
    shown = {f"user_00{n}" for n in range(1, 7) if f"/usuarios/user_00{n}\"" in text}
    assert shown == expected


def test_listado_con_api_caida(admin, front):
    with api_responds(front, httpx.ConnectError("x")):
        page = admin.get("/dashboard/usuarios")
    assert page.status_code == 503 and "API no disponible" in page.text


# --- Alta -------------------------------------------------------------------

def test_id_siguiente():
    ids = lambda *names: [{"external_id": name} for name in names]
    assert next_external_id(ids()) == "user_001"
    assert next_external_id(ids("user_001", "user_006", "user_invitado")) == "user_007"
    assert next_external_id(ids("user_099")) == "user_100"
    assert next_external_id(ids("user_1234")) == "user_1235"


def test_alta_genera_el_id_y_ofrece_asociar_tarjeta(admin, mock_state):
    response = post(admin, "/dashboard/usuarios/nuevo", nombre=" Fede ", apellido="Sosa", rol="alumno")
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/usuarios/user_007?creado=1"
    created = mock_state.find_user("user_007")
    assert (created["first_name"], created["last_name"], created["role"]) == ("Fede", "Sosa", "alumno")
    page = admin.get(response.headers["location"])
    assert "Usuario user_007 creado." in page.text
    assert "Asociar tarjeta ahora" in page.text
    assert "/dashboard/usuarios/user_007/rfid" in page.text


def test_alta_sin_datos_opcionales(admin, mock_state):
    assert post(admin, "/dashboard/usuarios/nuevo").status_code == 303
    created = mock_state.find_user("user_007")
    assert created["first_name"] is None and created["role"] is None


def test_alta_valida_el_largo(admin, mock_state):
    response = post(admin, "/dashboard/usuarios/nuevo", nombre="x" * 101, rol="y" * 51)
    assert response.status_code == 422
    assert "Máximo 100 caracteres." in response.text and "Máximo 50 caracteres." in response.text
    assert mock_state.find_user("user_007") is None


def test_alta_reintenta_si_el_id_ya_existe(admin, front):
    calls = {"post": 0}

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=[{"external_id": f"user_00{calls['post'] + 1}"}])
        calls["post"] += 1
        if calls["post"] < 3:
            return httpx.Response(409, json={"detail": "El usuario ya existe."})
        return httpx.Response(201, json={})

    with api_responds(front, handler):
        response = post_with_token(admin, "/dashboard/usuarios/nuevo", nombre="Fede")
    assert response.status_code == 303 and calls["post"] == 3
    assert response.headers["location"] == "/dashboard/usuarios/user_004?creado=1"


def test_alta_se_rinde_al_tercer_409(admin, front):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(409, json={"detail": "El usuario ya existe."})

    with api_responds(front, handler):
        response = post_with_token(admin, "/dashboard/usuarios/nuevo", nombre="Fede")
    assert response.status_code == 409
    assert "No se pudo generar un identificador libre" in response.text


def test_alta_muestra_422_de_la_api(admin, front):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(422, json={"detail": [
            {"loc": ["body", "first_name"], "msg": "Valor rechazado por la API"},
        ]})

    with api_responds(front, handler):
        response = post_with_token(admin, "/dashboard/usuarios/nuevo", nombre="Fede")
    assert response.status_code == 422 and "Valor rechazado por la API" in response.text


def post_with_token(client, path, **data):
    """Como `post`, pero pide el token antes de reemplazar la API."""
    return client.post(path, data=data, headers={"X-CSRF-Token": TOKENS[id(client)]})


TOKENS = {}


@pytest.fixture(autouse=True)
def remember_token(request):
    if "admin" in request.fixturenames:
        client = request.getfixturevalue("admin")
        TOKENS[id(client)] = csrf_of(client)


# --- Detalle y edición ------------------------------------------------------

def test_detalle(admin):
    page = admin.get("/dashboard/usuarios/user_001")
    assert page.status_code == 200
    text = page.text
    assert "Ana Pérez (user_001)" in text
    assert "Sí (2)" in text and "Revocar tarjeta" in text and "Revocar rostro" in text
    assert "El registro facial se realiza en el puesto de enrolamiento local" in text
    assert "Últimos accesos" in text
    assert "uid" not in text.lower()


def test_detalle_de_usuario_sin_nombre(admin):
    text = admin.get("/dashboard/usuarios/user_005").text
    assert "<h1>user_005" in text and "Asociar tarjeta" in text
    assert "Revocar tarjeta" not in text and "Revocar rostro" not in text


@pytest.mark.parametrize("external_id", ["user_999", "otra-cosa", "user_001%2F..%2Fstatus"])
def test_detalle_inexistente(admin, external_id):
    page = admin.get(f"/dashboard/usuarios/{external_id}")
    assert page.status_code == 404 and "No encontrado" in page.text


def test_viewer_ve_el_detalle_sin_acciones(viewer):
    text = viewer.get("/dashboard/usuarios/user_001").text
    assert "Ana Pérez (user_001)" in text
    for action in ("Guardar cambios", "Desactivar usuario", "Revocar", "Asociar tarjeta"):
        assert action not in text


def test_editar(admin, mock_state):
    response = post(admin, "/dashboard/usuarios/user_001/editar", nombre="Ana María", apellido="Pérez", rol="")
    assert response.status_code == 303
    user = mock_state.find_user("user_001")
    assert user["first_name"] == "Ana María" and user["role"] is None  # vacío borra el campo
    assert user["active"] is True  # editar nunca toca el estado
    assert "Datos del usuario actualizados." in admin.get(response.headers["location"]).text


def test_editar_invalido_no_llama_a_la_api(admin, mock_state):
    response = post(admin, "/dashboard/usuarios/user_001/editar", nombre="x" * 101)
    assert response.status_code == 422 and "Máximo 100 caracteres." in response.text
    assert mock_state.find_user("user_001")["first_name"] == "Ana"


def test_desactivar_y_reactivar_conserva_credenciales(admin, mock_state):
    assert "data-confirm" in admin.get("/dashboard/usuarios/user_001").text
    response = post(admin, "/dashboard/usuarios/user_001/estado", activo="no")
    assert response.status_code == 303
    user = mock_state.find_user("user_001")
    assert user["active"] is False and user["has_rfid"] and user["biometric_templates"] == 2
    page = admin.get("/dashboard/usuarios/user_001").text
    assert "ya no autoriza ingresos" in page and "Activar usuario" in page
    post(admin, "/dashboard/usuarios/user_001/estado", activo="si")
    assert mock_state.find_user("user_001")["active"] is True


def test_estado_invalido_no_cambia_nada(admin, mock_state):
    assert post(admin, "/dashboard/usuarios/user_001/estado", activo="quizas").status_code == 422
    assert post(admin, "/dashboard/usuarios/user_001/estado").status_code == 422
    assert mock_state.find_user("user_001")["active"] is True


def test_revocar_tarjeta_y_rostro(admin, mock_state):
    assert post(admin, "/dashboard/usuarios/user_001/tarjeta/revocar").status_code == 303
    assert mock_state.find_user("user_001")["has_rfid"] is False
    page = admin.get("/dashboard/usuarios/user_001").text
    assert "Tarjeta revocada." in page and "Asociar tarjeta" in page
    assert post(admin, "/dashboard/usuarios/user_001/rostro/revocar").status_code == 303
    assert mock_state.find_user("user_001")["biometric_templates"] == 0


def test_revocar_credencial_que_no_tiene(admin):
    response = post(admin, "/dashboard/usuarios/user_005/tarjeta/revocar")
    assert response.status_code == 303
    page = admin.get(response.headers["location"]).text
    assert "No encontrado (tarjeta): El usuario no posee una tarjeta activa." in page


def test_acciones_sobre_usuario_inexistente(admin):
    assert post(admin, "/dashboard/usuarios/user_999/editar", nombre="X").status_code == 404
    assert post(admin, "/dashboard/usuarios/user_999/estado", activo="no").status_code == 404
    assert post(admin, "/dashboard/usuarios/user_999/tarjeta/revocar").status_code == 404


# --- Permisos y CSRF --------------------------------------------------------

WRITES = [
    "/dashboard/usuarios/nuevo",
    "/dashboard/usuarios/user_001/editar",
    "/dashboard/usuarios/user_001/estado",
    "/dashboard/usuarios/user_001/tarjeta/revocar",
    "/dashboard/usuarios/user_001/rostro/revocar",
]


@pytest.mark.parametrize("path", WRITES)
def test_viewer_recibe_403_en_escrituras(viewer, mock_state, path):
    response = post(viewer, path, activo="no", nombre="Hack")
    assert response.status_code == 403
    user = mock_state.find_user("user_001")
    assert user["active"] and user["has_rfid"] and user["first_name"] == "Ana"
    assert len(mock_state.users) == 6


def test_viewer_no_ve_el_formulario_de_alta(viewer):
    assert viewer.get("/dashboard/usuarios/nuevo").status_code == 403


@pytest.mark.parametrize("path", WRITES)
def test_escrituras_sin_csrf_dan_403(admin, mock_state, path):
    assert admin.post(path, data={"activo": "no"}).status_code == 403
    assert mock_state.find_user("user_001")["active"] is True


@pytest.mark.parametrize("path", WRITES)
def test_escrituras_sin_sesion_redirigen(client, path):
    assert client.post(path, data={"activo": "no"}).status_code == 303


def test_ultimos_accesos_se_filtran_por_usuario(admin, mock_state):
    text = admin.get("/dashboard/usuarios/user_001").text
    own = [e for e in mock_state.events if e["external_id"] == "user_001"]
    assert text.count('id="evento-') == min(len(own), 20)


def test_ultimos_accesos_incompletos(admin, front, mock_state):
    user = mock_state.serialize_user(mock_state.find_user("user_006"))

    def handler(request):
        if request.url.path.endswith("/access-events"):
            return httpx.Response(200, json=[{
                "event_id": 1, "occurred_at": "2026-10-03T12:00:00-03:00", "method": "RFID",
                "external_id": "user_001", "granted": True, "restricted_time": False,
                "alert_reasons": [], "door_status": "simulated",
            }] * 500)
        return httpx.Response(200, json=user)

    with api_responds(front, handler):
        text = admin.get("/dashboard/usuarios/user_006").text
    assert "Sin accesos en los eventos recientes." in text
    assert "puede haber otros más antiguos" in text
