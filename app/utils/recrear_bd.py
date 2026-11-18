"""Recrea el esquema de la base desde cero, migra y carga datos de prueba.

Pensado para la base de QA, cuyo esquema quedó desactualizado: el despliegue
anterior creó las tablas nuevas con `crear_tablas`, pero nunca aplicó las
columnas ni los CHECK de las migraciones.

Por seguridad hay dos condiciones:
- exige CONFIRMAR_RECREAR_BD=si (borra todos los datos);
- si la base ya está versionada por Alembic no hace nada, así que dejar la
  variable definida no borra la base en cada despliegue.

Uso:
    CONFIRMAR_RECREAR_BD=si python -m app.utils.recrear_bd
"""

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.database import engine
from app.utils.datos_prueba import cargar

CONFIRMACION_VALIDA = {"si", "sí", "true", "1"}


def confirmado(valor: str | None) -> bool:
    return (valor or "").strip().lower() in CONFIRMACION_VALIDA


def ya_versionada(tablas: set[str]) -> bool:
    return "alembic_version" in tablas


def recrear() -> None:
    if not confirmado(os.getenv("CONFIRMAR_RECREAR_BD")):
        raise SystemExit(
            "Falta CONFIRMAR_RECREAR_BD=si: este comando borra todos los datos de la base."
        )
    if ya_versionada(set(inspect(engine).get_table_names())):
        print("La base ya está versionada con Alembic; no se recrea.")
        return

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    command.upgrade(Config("alembic.ini"), "head")
    cargar()
    print("Esquema recreado, migrado y con datos de prueba.")


if __name__ == "__main__":
    recrear()
