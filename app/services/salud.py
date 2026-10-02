"""Estado de la conexión a la base de datos, sin exponer detalles internos."""
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


def estado_bd(db: Session) -> str:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return "error"
    return "ok"
