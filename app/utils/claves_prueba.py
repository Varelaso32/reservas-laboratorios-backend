"""Asigna la clave de prueba a los usuarios @reservas.test que aún no tienen una.

Solo toca usuarios con dominio .test y clave "PENDIENTE_LOGIN". Se puede correr
varias veces. Uso: docker compose exec api python -m app.utils.claves_prueba
"""
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_clave
from app.models.modelos import Usuario

CLAVE_PRUEBA = "Reservas2026*"


def asignar() -> None:
    with SessionLocal() as db:
        usuarios = db.scalars(
            select(Usuario).where(
                Usuario.email.like("%@reservas.test"),
                Usuario.clave_hash == "PENDIENTE_LOGIN",
            )
        ).all()
        for u in usuarios:
            u.clave_hash = hash_clave(CLAVE_PRUEBA)
        db.commit()
    print(f"Clave asignada a {len(usuarios)} usuarios. Clave de prueba: {CLAVE_PRUEBA}")


if __name__ == "__main__":
    asignar()
