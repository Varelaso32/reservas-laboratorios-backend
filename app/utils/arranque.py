"""Prepara la base de datos antes de levantar la API.

Orden de trabajo (idempotente, se puede repetir en cada arranque):

1. Migra con Alembic, adoptando los esquemas viejos cuando hace falta
   (`migrar`). Es el único que crea o modifica tablas.
2. Verifica que la base quedó exactamente en `head` y con todas las tablas y
   columnas del modelo. Si no, **falla el arranque** con un mensaje claro en
   lugar de dejar la API devolviendo 500 en cada petición.

La recreación total (`RECREAR_BD`) queda como salida de emergencia y exige
además `CONFIRMAR_RECREAR_BD=si`: sin las dos variables no se borra nada.

Uso: python -m app.utils.arranque
"""

import os

from alembic.config import Config
from sqlalchemy import inspect

from app.core.database import engine
from app.utils.datos_prueba import cargar
from app.utils.esquema import revision_head, verificar
from app.utils.migrar import migrar
from app.utils.recrear_bd import CONFIRMACION_VALIDA, confirmado, recrear, version_actual


def recrear_solicitado(valor: str | None) -> bool:
    """True si la variable pide recrear, aceptando si/sí/true/1 en cualquier caso."""
    return (valor or "").strip().lower() in CONFIRMACION_VALIDA


def _recrear_si_se_pidio(version: str | None, head: str) -> None:
    """Recrea la base solo con las dos variables en afirmativo."""
    if not recrear_solicitado(os.getenv("RECREAR_BD")) or version == head:
        return
    if not confirmado(os.getenv("CONFIRMAR_RECREAR_BD")):
        print(
            "RECREAR_BD está definido, pero falta CONFIRMAR_RECREAR_BD=si: "
            "no se borra nada. La adopción automática del esquema sigue disponible."
        )
        return
    recrear()


def _verificar_o_fallar() -> None:
    """Corta el arranque si el esquema no quedó completo."""
    encontrados = verificar()
    if encontrados:
        detalle = "\n".join(f"- {problema}" for problema in encontrados)
        raise SystemExit(
            "El esquema de la base no quedó al día:\n"
            f"{detalle}\n"
            "Revisar las migraciones en migrations/versions y volver a desplegar. "
            "No se crea nada automáticamente para no dejar tablas sin versionar."
        )


def preparar() -> None:
    config = Config("alembic.ini")
    head = revision_head(config)
    tablas = set(inspect(engine).get_table_names())
    version = version_actual(tablas)
    print(f"RECREAR_BD={os.getenv('RECREAR_BD')!r} | versión={version} | head={head}")

    _recrear_si_se_pidio(version, head)

    if migrar():
        # Se adoptó un esquema anterior: se restauran los catálogos de ejemplo.
        cargar()

    _verificar_o_fallar()
    print(f"Esquema verificado en {head}")


if __name__ == "__main__":
    preparar()
