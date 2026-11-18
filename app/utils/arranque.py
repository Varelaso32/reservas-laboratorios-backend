"""Prepara la base de datos al arrancar la API.

- Si `RECREAR_BD` tiene un valor afirmativo (si, sí, true, 1, sin importar
  mayúsculas) y la base no está en la última revisión, la recrea, migra y
  siembra datos de prueba. Es la salida para la base de QA, que quedó con
  tablas nuevas creadas por `create_all` y sin las columnas de las migraciones.
- Después aplica las migraciones pendientes (idempotente).

Uso: python -m app.utils.arranque
"""

import os

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from app.core.database import engine
from app.utils.datos_prueba import cargar
from app.utils.migrar import migrar
from app.utils.recrear_bd import CONFIRMACION_VALIDA, recrear, version_actual


def recrear_solicitado(valor: str | None) -> bool:
    """True si la variable pide recrear, aceptando si/sí/true/1 en cualquier caso."""
    return (valor or "").strip().lower() in CONFIRMACION_VALIDA


def preparar() -> None:
    config = Config("alembic.ini")
    head = ScriptDirectory.from_config(config).get_current_head()
    tablas = set(inspect(engine).get_table_names())
    version = version_actual(tablas)
    print(f"RECREAR_BD={os.getenv('RECREAR_BD')!r} | versión={version} | head={head}")

    if recrear_solicitado(os.getenv("RECREAR_BD")) and version != head:
        # El arranque ya fue autorizado por RECREAR_BD: se confirma para el script.
        os.environ["CONFIRMAR_RECREAR_BD"] = "si"
        recrear()

    if migrar():
        # Se adoptó un esquema anterior: se restauran los catálogos de ejemplo.
        cargar()


if __name__ == "__main__":
    preparar()
