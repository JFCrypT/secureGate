"""Dashboard: estado del sistema y acceso en tiempo real."""

from fastapi import APIRouter, Request

from app.templating import render


router = APIRouter()


@router.get("/")
async def index(request: Request):
    return render(request, "inicio.html", {"section": "dashboard"})
