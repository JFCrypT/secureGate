"""Login y logout de operadores."""

import logging
import math

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app import auth
from app.templating import render


logger = logging.getLogger("securegate.front.auth")
router = APIRouter(dependencies=[Depends(auth.page_context)])


def _home(request):
    return f"{request.app.state.settings.base_path}/"


@router.get("/login")
async def login_form(request: Request):
    if request.state.operator:
        return RedirectResponse(_home(request), status_code=303)
    return render(request, "login.html")


@router.post("/login", dependencies=[Depends(auth.verify_csrf)])
async def login(request: Request, usuario: str = Form(""), clave: str = Form("")):
    limiter = request.app.state.login_limiter
    ip = auth.client_ip(request)
    blocked = limiter.blocked_seconds(ip)
    if blocked:
        minutes = max(1, math.ceil(blocked / 60))
        return render(request, "login.html", {
            "error": f"Demasiados intentos fallidos. Probá de nuevo en {minutes} min.",
        }, status_code=429)

    username = usuario.strip().lower()
    operator = request.app.state.operators.verify(username, clave)
    if operator is None:
        limiter.register_failure(ip)
        logger.warning("Login fallido desde %s.", ip)
        return render(request, "login.html", {
            "error": "Usuario o contraseña incorrectos.", "usuario": username,
        }, status_code=401)

    limiter.reset(ip)
    auth.start_session(request, operator)
    logger.info("Login de %s (%s) desde %s.", operator["usuario"], operator["rol"], ip)
    return RedirectResponse(_home(request), status_code=303)


@router.post("/logout", dependencies=[Depends(auth.verify_csrf)])
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(f"{request.app.state.settings.base_path}/login", status_code=303)
