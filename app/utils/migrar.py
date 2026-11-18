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
from sqlalchemy.exc import ProgrammingError

from app.core.database import engine

# Primera revisión versionada: reproduce el esquema que creaba crear_tablas.
REVISION_BASE = "0001_baseline"
# Tabla que solo existe si la base viene de crear_tablas (esquema anterior).
TABLA_ANTERIOR = "usuario"
# Tablas que solo existen a partir de la migración 0002.
TABLAS_POSTERIORES = ("tipo_uso", "notificacion", "recurso", "registro_configuracion")


def es_base_anterior(tablas: set[str]) -> bool:
    """True si la base es anterior a Alembic y hay que marcarla como baseline."""
    return "alembic_version" not in tablas and TABLA_ANTERIOR in tablas


def esta_contaminada(tablas: set[str]) -> bool:
    """True si create_all creó tablas de la 0002+ antes de versionar el esquema.

    Pasa en la base de QA: tiene tablas nuevas pero no las columnas ni los CHECK
    de las migraciones, así que aplicarlas fallaría con "ya existe". En ese caso
    hay que recrear el esquema (app.utils.recrear_bd) en vez de migrar.
    """
    return es_base_anterior(tablas) and any(t in tablas for t in TABLAS_POSTERIORES)


def migrar() -> None:
    config = Config("alembic.ini")
    tablas = set(inspect(engine).get_table_names())
    if esta_contaminada(tablas):
        raise SystemExit(
            "La base tiene tablas del Sprint 2 sin las migraciones aplicadas. "
            "Definir RECREAR_BD=si (y CONFIRMAR_RECREAR_BD=si) para recrearla."
        )
    if es_base_anterior(tablas):
        command.stamp(config, REVISION_BASE)
        print(f"Base existente marcada como {REVISION_BASE}")
    try:
        command.upgrade(config, "head")
    except ProgrammingError as exc:
        if "already exists" in str(exc.orig):
            raise SystemExit(
                "La base quedó a medio migrar: tiene tablas sin la versión de Alembic "
                "que las creó. Definir RECREAR_BD=si (y CONFIRMAR_RECREAR_BD=si) para "
                "recrearla, o aplicar la migración a mano."
            ) from exc
        raise
    print("Migraciones al día")


if __name__ == "__main__":
    migrar()
