from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.salud import estado_bd

router = APIRouter(tags=["salud"])


@router.get("/salud")
def salud(db: Session = Depends(get_db)) -> dict[str, str]:
    return {"estado": "ok", "bd": estado_bd(db)}
