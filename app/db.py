"""Engine y sesión de base de datos (SQLAlchemy 2.0 + psycopg v3)."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().url_bd(), pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
