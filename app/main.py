"""Aplicación FastAPI: API en /v1 y pantallas en /app."""
from pathlib import Path

from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.core.errors import registrar_manejadores
from app.db import get_db
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
    perfil,
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


def _url_publica(request: Request) -> str:
    """La "URL pública del sistema" (config_sistema), con la misma sesión que usan las rutas (en las pruebas, la del test)."""
    from app.services import sistema

    proveedor = request.app.dependency_overrides.get(get_db, get_db)
    generador = proveedor()
    db = next(generador)
    try:
        return sistema.url_publica(db)
    finally:
        generador.close()


@app.middleware("http")
async def sin_run_app(request: Request, siguiente):
    """Baja de run.app: por la URL de Cloud Run (*.run.app) solo siguen /internal/* (Cloud Scheduler y el callback de
    Tencent, como red de seguridad) y /v1/salud. GET y HEAD → 301 a la misma ruta y query en la URL pública del sistema;
    los demás métodos → 410 con el dominio a usar. El destino sale de config_sistema, nunca fijo en el código. Si la URL
    pública también es run.app (por ejemplo, en la base de pruebas), no se redirige."""
    host = request.headers.get("host", "").split(":")[0].lower()
    ruta = request.url.path
    if not host.endswith(".run.app") or ruta.startswith("/internal/") or ruta == "/v1/salud":
        return await siguiente(request)
    publica = await run_in_threadpool(_url_publica, request)
    destino_host = (urlsplit(publica).hostname or "").lower()
    if not destino_host or destino_host.endswith(".run.app") or destino_host == host:
        return await siguiente(request)
    if request.method in ("GET", "HEAD"):
        return RedirectResponse(publica + ruta + (f"?{request.url.query}" if request.url.query else ""), status_code=301)
    return JSONResponse(status_code=410, content={"detail": {
        "codigo": "USE_DOMINIO_PROPIO", "mensaje": f"Esta dirección ya no se usa. Use {publica}"}})

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
api.include_router(perfil.router)  # E1-B: antes de clientes (rutas fijas /clientes/…)
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
