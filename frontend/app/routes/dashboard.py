"""Dashboard: estado del sistema y acceso en tiempo real."""

from fastapi import APIRouter, Request

from app.routes.partials import estado_context, tiempo_real_context
from app.templating import render


router = APIRouter()


@router.get("/")
async def index(request: Request):
    context = {"section": "dashboard"}
    context.update(await estado_context(request))
    context.update(await tiempo_real_context(request))
    return render(request, "dashboard.html", context)
