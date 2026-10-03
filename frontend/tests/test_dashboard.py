import httpx

from tests.conftest import TEST_TOKEN, api_responds


def test_dashboard_muestra_estado_y_ultimo_acceso(admin, mock_state):
    page = admin.get("/dashboard/")
    assert page.status_code == 200
    text = page.text
    assert "ONLINE" in text and "OFFLINE" not in text
    assert "Biometría + RFID" in text
    assert "modo simulación" in text  # banner ámbar
    assert "Último heartbeat" in text and "(hace " in text
    assert "Último acceso" in text and "Últimos 10 accesos" in text
    last = mock_state.events[-1]
    assert f'data-event-id="{last["event_id"]}"' in text
    assert 'hx-trigger="every 5000ms"' in text and 'hx-trigger="every 2000ms"' in text
    assert TEST_TOKEN not in text


def test_viewer_tambien_ve_el_dashboard(viewer):
    assert viewer.get("/dashboard/").status_code == 200
    assert viewer.get("/dashboard/partials/estado").status_code == 200


def test_parciales_piden_sesion(client):
    assert client.get("/dashboard/partials/estado").status_code == 303
    response = client.get("/dashboard/partials/tiempo-real", headers={"HX-Request": "true"})
    assert response.status_code == 401 and "hx-redirect" in response.headers


def test_runtime_offline(admin, mock_state):
    mock_state.offline = "1"
    text = admin.get("/dashboard/partials/estado").text
    assert "OFFLINE" in text and "heartbeat está vencido" in text
    mock_state.offline = "unknown"
    text = admin.get("/dashboard/partials/estado").text
    assert "OFFLINE" in text and "Sin datos" in text
    assert "modo simulación" not in text  # no se inventa el modo de puerta


def test_puerta_gpio_no_muestra_banner_de_simulacion(admin, mock_state):
    mock_state.door_mode = "gpio"
    text = admin.get("/dashboard/partials/estado").text
    assert "GPIO (puerta real)" in text and "modo simulación" not in text


def test_evento_nuevo_aparece_en_tiempo_real(admin, mock_state):
    admin.get("/dashboard/partials/tiempo-real")
    event = mock_state.add_event()
    text = admin.get("/dashboard/partials/tiempo-real").text
    assert f'data-event-id="{event["event_id"]}"' in text


def test_desconocido_se_muestra_como_no_autorizado(admin, mock_state):
    mock_state.events.append({
        "event_id": 999, "occurred_at": "2026-10-03T12:00:00-03:00", "method": "facial",
        "external_id": None, "granted": False, "restricted_time": False,
        "alert_reasons": [], "door_status": "not_requested",
    })
    text = admin.get("/dashboard/partials/tiempo-real").text
    assert "Desconocido" in text and "NO AUTORIZADO" in text and "Biometría" in text


def test_simulada_no_se_muestra_como_abierta(admin, mock_state):
    mock_state.events.append({
        "event_id": 999, "occurred_at": "2026-10-03T12:00:00-03:00", "method": "RFID",
        "external_id": "user_001", "granted": True, "restricted_time": False,
        "alert_reasons": [], "door_status": "simulated",
    })
    text = admin.get("/dashboard/partials/tiempo-real").text
    card = text.split("</section>")[0]
    assert "Simulada — sin apertura física" in card and "Abierta" not in card
    assert "Ana Pérez (user_001)" in card and "AUTORIZADO" in card


def test_api_caida_muestra_ultimos_datos_desactualizados(admin, front):
    assert "ONLINE" in admin.get("/dashboard/").text
    with api_responds(front, httpx.ConnectError("x")):
        page = admin.get("/dashboard/")
        assert page.status_code == 200
        assert "API no disponible" in page.text
        assert "(desactualizado)" in page.text
        assert "Último acceso" in page.text  # sigue mostrando lo último conocido
    # Al volver la API se recupera sola.
    text = admin.get("/dashboard/").text
    assert "API no disponible" not in text and "(desactualizado)" not in text


def test_api_caida_sin_datos_previos(admin, front):
    with api_responds(front, httpx.ReadTimeout("x")):
        page = admin.get("/dashboard/")
    assert page.status_code == 200
    assert "API no disponible" in page.text
    assert "ONLINE" not in page.text and "OFFLINE" not in page.text  # no se inventa estado


def test_401_del_token_no_desloguea_al_operador(admin, front):
    unauthorized = httpx.Response(401, json={"detail": "Token de API inválido o ausente."})
    with api_responds(front, lambda request: unauthorized):
        text = admin.get("/dashboard/partials/estado").text
    assert "Error de configuración del servidor" in text
    assert admin.get("/dashboard/").status_code == 200


def test_base_de_datos_caida(admin, mock_state):
    mock_state.db_down = True
    text = admin.get("/dashboard/partials/estado").text
    assert "Base de datos no disponible" in text
