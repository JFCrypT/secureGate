def test_la_raiz_redirige_al_dashboard(client):
    for path in ("/", "/dashboard"):
        response = client.get(path)
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard/"


def test_estaticos_vendorizados_y_sin_urls_externas(client):
    for name in ("htmx.min.js", "app.css", "app.js"):
        response = client.get(f"/dashboard/static/{name}")
        assert response.status_code == 200
        assert "http://" not in response.text and "https://" not in response.text


def test_cabeceras_de_seguridad(client):
    response = client.get("/dashboard/login")
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_pagina_inexistente(admin):
    response = admin.get("/dashboard/no-existe")
    assert response.status_code == 404 and "No encontrado" in response.text
