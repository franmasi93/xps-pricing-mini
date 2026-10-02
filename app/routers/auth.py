from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rbac import get_usuario_actual, permisos_de
from app.db import get_db
from app.models import Usuario
from app.schemas.auth import CambiarPasswordEntrada, LoginEntrada, TokenSalida, YoSalida
from app.schemas.usuarios import RolResumen
from app.services import auth as servicio

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenSalida)
def login(datos: LoginEntrada, db: Session = Depends(get_db)) -> TokenSalida:
    token, forzar = servicio.login(db, datos.email, datos.password)
    return TokenSalida(access_token=token, forzar_cambio_password=forzar)


@router.get("/yo", response_model=YoSalida)
def yo(usuario: Usuario = Depends(get_usuario_actual)) -> YoSalida:
    return YoSalida(
        id=usuario.id,
        email=usuario.email,
        nombre=usuario.nombre,
        rol=RolResumen.model_validate(usuario.rol),
        permisos=sorted(permisos_de(usuario)),
        forzar_cambio_password=usuario.forzar_cambio_password,
        ultimo_login=usuario.ultimo_login,
    )


@router.post("/cambiar-password", response_model=TokenSalida)
def cambiar_password(
    datos: CambiarPasswordEntrada,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
) -> TokenSalida:
    token = servicio.cambiar_password(db, usuario, datos.password_actual, datos.password_nueva)
    return TokenSalida(access_token=token, forzar_cambio_password=False)
