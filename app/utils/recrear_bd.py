"""Recrea el esquema de la base desde cero, migra y carga datos de prueba.

Pensado para la base de QA, cuyo esquema quedó desactualizado: el despliegue
anterior creó las tablas nuevas con `crear_tablas`, pero nunca aplicó las
columnas ni los CHECK de las migraciones.

Por seguridad hay dos condiciones:
- exige CONFIRMAR_RECREAR_BD=si (borra todos los datos);
- no hace nada si la base ya está migrada hasta `head`, así que dejar la
  variable definida no borra la base en cada despliegue.

Si la base quedó a medio migrar (versión distinta de `head`), también la
recrea, porque las migraciones no se pueden aplicar dos veces.

Uso:
    CONFIRMAR_RECREAR_BD=si python -m app.utils.recrear_bd
"""

import os

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.core.database import engine
from app.utils.datos_prueba import cargar

CONFIRMACION_VALIDA = {"si", "sí", "true", "1"}


def confirmado(valor: str | None) -> bool:
    return (valor or "").strip().lower() in CONFIRMACION_VALIDA


def version_actual(tablas: set[str], motor=None) -> str | None:
    """Versión de Alembic aplicada, o None si la base no está versionada."""
    if "alembic_version" not in tablas:
        return None
    with (motor or engine).connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def al_dia(version: str | None, head: str) -> bool:
    return version == head


def recrear() -> None:
    if not confirmado(os.getenv("CONFIRMAR_RECREAR_BD")):
        raise SystemExit(
            "Falta CONFIRMAR_RECREAR_BD=si: este comando borra todos los datos de la base."
        )

    config = Config("alembic.ini")
    head = ScriptDirectory.from_config(config).get_current_head()
    tablas = set(inspect(engine).get_table_names())
    if al_dia(version_actual(tablas), head):
        print(f"La base ya está migrada en {head}; no se recrea.")
        return

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    command.upgrade(config, "head")
    cargar()
    print("Esquema recreado, migrado y con datos de prueba.")


if __name__ == "__main__":
    recrear()
