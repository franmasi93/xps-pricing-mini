"""Harness de tests con SAVEPOINT (sección 16.1 del documento rector).

Cada test corre dentro de una transacción externa que se revierte al final.
Los commit() del código de la aplicación solo liberan un SAVEPOINT.
Sin TRUNCATE, sin begin_nested() manual, sin listeners after_commit.
"""
import os

# Los tests SIEMPRE usan xps_pricing_test; debe fijarse antes de importar la app.
os.environ["APP_ENV"] = "test"

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import crear_token, hashear_password
from app.db import engine, get_db
from app.main import app
from app.models import Rol, Usuario

PASSWORD_PRUEBA = "ClavePrueba2026"


@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    def _get_db_de_test():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_de_test
    try:
        with TestClient(app) as cliente:
            yield cliente
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def crear_usuario(db_session):
    """Fábrica: cada test crea sus propios usuarios, con email único; nunca IDs fijos."""

    def _crear(
        rol_codigo: str = "comercial",
        password: str = PASSWORD_PRUEBA,
        activo: bool = True,
        forzar: bool = False,
        email: str | None = None,
        nombre: str | None = None,
    ) -> Usuario:
        rol = db_session.scalars(select(Rol).where(Rol.codigo == rol_codigo)).one()
        usuario = Usuario(
            email=email or f"u{uuid4().hex[:12]}@prueba.xps",
            nombre=nombre or f"Usuario {rol_codigo}",
            hash_password=hashear_password(password),
            rol=rol,
            activo=activo,
            forzar_cambio_password=forzar,
        )
        db_session.add(usuario)
        db_session.commit()
        return usuario

    return _crear


@pytest.fixture
def headers_de():
    """Encabezado Authorization con un token vigente del usuario."""

    def _headers(usuario: Usuario) -> dict[str, str]:
        return {"Authorization": f"Bearer {crear_token(usuario.id, usuario.token_version)}"}

    return _headers
