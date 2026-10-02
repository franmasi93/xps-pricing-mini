"""Canario PERMANENTE de aislamiento entre tests.

El test A inserta una fila y hace commit; el test B (que corre después, en orden
de archivo) verifica que esa fila NO existe. Si B falla, el harness está filtrando
datos entre tests y ningún otro resultado de la suite es confiable.
"""
from sqlalchemy import text

CODIGO_CANARIO = "zz_canario_aislamiento"


def test_a_inserta_y_hace_commit(db_session):
    db_session.execute(
        text("INSERT INTO rol (codigo, nombre) VALUES (:codigo, 'Canario de aislamiento')"),
        {"codigo": CODIGO_CANARIO},
    )
    db_session.commit()
    total = db_session.execute(
        text("SELECT COUNT(*) FROM rol WHERE codigo = :codigo"), {"codigo": CODIGO_CANARIO}
    ).scalar_one()
    assert total == 1


def test_b_la_fila_del_test_a_no_existe(db_session):
    total = db_session.execute(
        text("SELECT COUNT(*) FROM rol WHERE codigo = :codigo"), {"codigo": CODIGO_CANARIO}
    ).scalar_one()
    assert total == 0
