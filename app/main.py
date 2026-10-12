"""Aplicación FastAPI: API en /v1 y pantallas en /app."""
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.errors import registrar_manejadores
from app.routers import (
    auth,
    catalogos,
    clientes,
    cotizaciones,
    geografia,
    monedas,
    proveedores,
    roles,
    salud,
    tarifas,
    usuarios,
)

DIR_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
RUTA_LOGIN = "/app/login.html"

app = FastAPI(title="XPS Pricing Mini", version="1.0")
registrar_manejadores(app)

api = APIRouter(prefix="/v1")
api.include_router(salud.router)
api.include_router(auth.router)
api.include_router(roles.router)
api.include_router(usuarios.router)
api.include_router(geografia.router)
api.include_router(monedas.router)
api.include_router(proveedores.router)
api.include_router(catalogos.router)
api.include_router(tarifas.router)
api.include_router(clientes.router)
api.include_router(cotizaciones.router)
app.include_router(api)


@app.get("/", include_in_schema=False)
@app.get("/app", include_in_schema=False)
@app.get("/app/", include_in_schema=False)
def ir_al_login() -> RedirectResponse:
    return RedirectResponse(RUTA_LOGIN)


app.mount("/app", StaticFiles(directory=DIR_FRONTEND), name="app")
