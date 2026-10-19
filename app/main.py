"""Aplicación FastAPI: API en /v1 y pantallas en /app."""
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.errors import registrar_manejadores
from app.routers import (
    administracion,
    auth,
    boletines,
    catalogos,
    clientes,
    correo,
    cotizaciones,
    geografia,
    internos,
    monedas,
    notificaciones,
    proveedores,
    roles,
    salud,
    servicios,
    tarifas,
    usuarios,
)

DIR_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
RUTA_LOGIN = "/app/login.html"

app = FastAPI(title="XPS Pricing Mini", version="1.0")
registrar_manejadores(app)


@app.middleware("http")
async def sin_www(request: Request, siguiente):
    """E4: www.<dominio> → <dominio> (301; 308 si no es GET/HEAD, para no perder el cuerpo). El sistema responde igual
    con cualquier otro dominio (el de Cloud Run o el propio): no hay CORS ni cookies, y la API usa rutas relativas."""
    host = request.headers.get("host", "")
    if host.lower().startswith("www."):
        destino = f"https://{host[4:]}{request.url.path}" + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(destino, status_code=301 if request.method in ("GET", "HEAD") else 308)
    return await siguiente(request)

api = APIRouter(prefix="/v1")
api.include_router(salud.router)
api.include_router(auth.router)
api.include_router(roles.router)
api.include_router(usuarios.router)
api.include_router(geografia.router)
api.include_router(monedas.router)
api.include_router(proveedores.router)
api.include_router(catalogos.router)
api.include_router(servicios.router)
api.include_router(tarifas.router)
api.include_router(clientes.router)
api.include_router(cotizaciones.router)
api.include_router(correo.router)
api.include_router(boletines.router)
api.include_router(administracion.router)  # E2
api.include_router(notificaciones.router)  # E3
app.include_router(api)
app.include_router(internos.router_internos)  # E1: Cloud Scheduler y callback de Tencent (sin JWT)
app.include_router(internos.router_publico)  # E1: baja pública


@app.get("/", include_in_schema=False)
@app.get("/app", include_in_schema=False)
@app.get("/app/", include_in_schema=False)
def ir_al_login() -> RedirectResponse:
    return RedirectResponse(RUTA_LOGIN)


app.mount("/app", StaticFiles(directory=DIR_FRONTEND), name="app")
