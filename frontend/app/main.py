"""Aplicación del front: `uvicorn app.main:app --host 0.0.0.0 --port 8080`.

Un solo worker: el rate limit de login y las cachés viven en memoria.
"""

import logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api_client import SecureGateClient
from app.config import ConfigError, load_env_file, load_settings
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
    base = settings.base_path

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if not request.url.path.startswith(f"{base}/static/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.mount(f"{base}/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    @app.get("/", include_in_schema=False)
    @app.get(base, include_in_schema=False)
    async def root():
        return RedirectResponse(f"{base}/", status_code=302)

    router = APIRouter(prefix=base)

    @router.get("/")
    async def index(request: Request):
        return render(request, "inicio.html")

    app.include_router(router)
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
