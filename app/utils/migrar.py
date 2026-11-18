"""Aplica las migraciones de Alembic al arrancar la API.

Las bases de los ambientes se crearon con `crear_tablas` antes de versionar el
esquema, así que no tienen la tabla `alembic_version`. En ese caso se marcan
como `0001_baseline` sin ejecutar la migración y luego se aplican las demás.

Es idempotente: correrlo varias veces no cambia nada.

Uso: python -m app.utils.migrar
"""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.core.database import engine

# Primera revisión versionada: reproduce el esquema que creaba crear_tablas.
REVISION_BASE = "0001_baseline"
# Tabla que solo existe si la base viene de crear_tablas (esquema anterior).
TABLA_ANTERIOR = "usuario"


def es_base_anterior(tablas: set[str]) -> bool:
    """True si la base es anterior a Alembic y hay que marcarla como baseline."""
    return "alembic_version" not in tablas and TABLA_ANTERIOR in tablas


def migrar() -> None:
    config = Config("alembic.ini")
    tablas = set(inspect(engine).get_table_names())
    if es_base_anterior(tablas):
        command.stamp(config, REVISION_BASE)
        print(f"Base existente marcada como {REVISION_BASE}")
    command.upgrade(config, "head")
    print("Migraciones al día")


if __name__ == "__main__":
    migrar()
