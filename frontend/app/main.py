"""Aplicación del front: `uvicorn app.main:app --host 0.0.0.0 --port 8080`.

Un solo worker: el rate limit de login y las cachés viven en memoria.
"""

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app import auth
from app.api_client import (
    ApiBackendError,
    ApiConfigError,
    ApiError,
    ApiNotFound,
    ApiUnavailable,
    SecureGateClient,
)
from app.config import ConfigError, load_env_file, load_settings
from app.routes import dashboard, partials, sesion
from app.templating import APP_DIR, render


logger = logging.getLogger("securegate.front")

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


def create_app(settings=None, api_transport=None):
    """`api_transport` permite a los tests conectar el cliente a una API falsa."""
    if settings is None:
        load_env_file()
        settings = load_settings()

    app = FastAPI(title="secureGate — dashboard", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.api = SecureGateClient(
        settings.api_url, settings.api_token, transport=api_transport
    )
    app.state.operators = auth.OperatorStore(settings.operators_file)
    app.state.login_limiter = auth.LoginRateLimiter()
    base = settings.base_path

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if not request.url.path.startswith(f"{base}/static/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    # Cookie firmada, HttpOnly y SameSite=Lax. Sin Secure: el lab usa HTTP plano.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="securegate_session",
        max_age=settings.session_hours * 3600,
        same_site="lax",
        https_only=False,
    )

    app.mount(f"{base}/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    @app.get("/", include_in_schema=False)
    @app.get(base, include_in_schema=False)
    async def root():
        return RedirectResponse(f"{base}/", status_code=302)

    def error_page(request, status_code, title, message):
        if request.headers.get("HX-Request"):
            return Response(message, status_code=status_code, media_type="text/plain")
        return render(request, "error.html", {"title": title, "message": message},
                      status_code=status_code)

    @app.exception_handler(auth.NotAuthenticated)
    async def not_authenticated(request, exc):
        login = f"{base}/login"
        if request.headers.get("HX-Request"):
            # HTMX no sigue un 303 como navegación: se le pide que redirija.
            return Response(status_code=401, headers={"HX-Redirect": login})
        return RedirectResponse(login, status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        if exc.status_code == 404 and auth.current_operator(request) is None:
            # Sin sesión no se revela qué rutas existen: todo va al login.
            return await not_authenticated(request, exc)
        titles = {403: "Acceso denegado", 404: "No encontrado"}
        messages = {404: "La página no existe.", 405: "Método no permitido."}
        detail = exc.detail if exc.status_code == 403 else None
        return error_page(
            request, exc.status_code,
            titles.get(exc.status_code, "Error"),
            detail or messages.get(exc.status_code, "No se pudo completar el pedido."),
        )

    @app.exception_handler(ApiError)
    async def api_error(request, exc):
        # Errores de la API que ninguna ruta manejó con más contexto (§4.5).
        if isinstance(exc, ApiNotFound):
            return error_page(request, 404, "No encontrado", exc.message)
        if isinstance(exc, ApiConfigError):
            return error_page(request, 502, exc.message,
                              "El front no pudo autenticarse contra la API. Avisá al administrador.")
        if isinstance(exc, ApiUnavailable):
            return error_page(request, 503, exc.message,
                              "No se pudo conectar con la API de secureGate. Probá de nuevo en unos segundos.")
        if isinstance(exc, ApiBackendError):
            return error_page(request, 503, exc.message, "La API no pudo leer la base de datos.")
        return error_page(request, 502, "Error", exc.message)

    app.include_router(sesion.router, prefix=base)
    private = [Depends(auth.require_login)]
    for module in (dashboard, partials):
        app.include_router(module.router, prefix=base, dependencies=private)
    return app


def __getattr__(name):
    # `app` se crea recién cuando uvicorn lo pide, así importar este módulo
    # (tests, cli) no exige tener el entorno configurado.
    if name == "app":
        try:
            application = create_app()
        except ConfigError as exc:
            raise SystemExit(f"\n{exc}\n") from None
        globals()["app"] = application
        return application
    raise AttributeError(name)
