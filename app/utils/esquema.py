"""Comprueba que el esquema de la base esté al día con las migraciones.

Se usa en dos lugares:

- `app.utils.arranque`, antes de levantar la API: si algo no cuadra, el
  despliegue falla con un mensaje claro en vez de arrancar y devolver 500 en
  las peticiones.
- `GET /salud`, que es el *health check* de Render: solo responde 200 cuando
  la base conecta y el esquema está completo.

No modifica nada: solo lee la base.

Uso: python -m app.utils.esquema
"""

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.core.database import Base, engine
from app.models import modelos  # noqa: F401  (registra las tablas en Base)
from app.utils.recrear_bd import version_actual


def revision_head(config: Config | None = None) -> str:
    """Última revisión de Alembic (la que debe tener la base)."""
    return ScriptDirectory.from_config(config or Config("alembic.ini")).get_current_head()


def tablas_faltantes(tablas: set[str], esperadas: set[str] | None = None) -> list[str]:
    """Tablas del modelo que no existen en la base (ordenadas)."""
    return sorted((esperadas or set(Base.metadata.tables)) - tablas)


def columnas_faltantes(inspector, tablas: set[str]) -> dict[str, list[str]]:
    """Columnas del modelo que faltan en tablas que sí existen."""
    faltan: dict[str, list[str]] = {}
    for nombre, tabla in Base.metadata.tables.items():
        if nombre not in tablas:
            continue
        reales = {columna["name"] for columna in inspector.get_columns(nombre)}
        esperadas = {columna.name for columna in tabla.columns}
        if esperadas - reales:
            faltan[nombre] = sorted(esperadas - reales)
    return faltan


def problemas_del_esquema(
    version: str | None,
    head: str,
    faltantes_tablas: list[str],
    faltantes_columnas: dict[str, list[str]],
) -> list[str]:
    """Lista legible de problemas. Vacía significa que el esquema está al día."""
    problemas: list[str] = []
    if version != head:
        problemas.append(
            f"La versión de la base es {version or 'ninguna'} y debería ser {head}: "
            "faltan migraciones por aplicar."
        )
    if faltantes_tablas:
        problemas.append(
            "Faltan tablas en la base: "
            + ", ".join(faltantes_tablas)
            + ". Alguna migración no se aplicó."
        )
    for tabla, columnas in sorted(faltantes_columnas.items()):
        problemas.append(
            f"A la tabla {tabla} le faltan columnas: {', '.join(columnas)}."
        )
    return problemas


def verificar(motor: Engine | None = None) -> list[str]:
    """Problemas del esquema actual (vacío si todo está bien)."""
    motor = motor or engine
    inspector = inspect(motor)
    tablas = set(inspector.get_table_names())
    return problemas_del_esquema(
        version=version_actual(tablas, motor),
        head=revision_head(),
        faltantes_tablas=tablas_faltantes(tablas),
        faltantes_columnas=columnas_faltantes(inspector, tablas),
    )


if __name__ == "__main__":
    encontrados = verificar()
    if encontrados:
        print("Esquema incompleto:")
        for problema in encontrados:
            print(f"- {problema}")
        raise SystemExit(1)
    print(f"Esquema al día en {revision_head()}")
