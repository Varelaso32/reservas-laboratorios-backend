"""Aplica las migraciones de Alembic al arrancar la API.

Contempla los tres estados posibles de una base:

1. **Vacía**: se migra desde cero.
2. **Anterior a Alembic** (creada con `crear_tablas`, sin `alembic_version`):
   se marca como `0001_baseline` y se aplican las migraciones pendientes.
3. **Anterior con tablas del Sprint 2** (las creó `create_all` sin las columnas
   ni los CHECK de las migraciones): se "adopta" el esquema, es decir, se
   eliminan solo esas tablas nuevas y se aplican las migraciones. Los datos de
   usuarios, espacios, solicitudes, reservas y trazabilidad se conservan.

Es idempotente: correrlo varias veces no cambia nada.

Uso: python -m app.utils.migrar
"""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError

from app.core.database import engine

# Primera revisión versionada: reproduce el esquema que creaba crear_tablas.
REVISION_BASE = "0001_baseline"
# Tabla que solo existe si la base viene de crear_tablas (esquema anterior).
TABLA_ANTERIOR = "usuario"
# Columnas que solo existen después de aplicar la migración 0002.
COLUMNA_SPRINT_2 = "puede_autorizar_especial"
# Tablas del esquema base (0001). Todo lo demás lo crean las migraciones 0002+.
TABLAS_BASE = frozenset(
    {"espacio", "espacio_aprobador", "reserva", "solicitud", "trazabilidad", "usuario"}
)
# Tablas creadas por las migraciones 0002 a 0007.
TABLAS_POSTERIORES = frozenset(
    {
        "asignacion_recurso",
        "detalle_solicitud_recurso",
        "espacio_tipo_uso",
        "notificacion",
        "parametro_sancion",
        "reactivacion",
        "recurso",
        "registro_configuracion",
        "regla_anticipacion_rol",
        "solicitud_recurso",
        "strike",
        "tipo_recurso",
        "tipo_uso",
    }
)


def es_base_anterior(tablas: set[str]) -> bool:
    """True si la base es anterior a Alembic y hay que marcarla como baseline."""
    return "alembic_version" not in tablas and TABLA_ANTERIOR in tablas


def esta_contaminada(tablas: set[str]) -> bool:
    """True si create_all creó tablas de la 0002+ antes de versionar el esquema."""
    return es_base_anterior(tablas) and any(t in tablas for t in TABLAS_POSTERIORES)


def necesita_adoptar(tablas: set[str], columnas_usuario: set[str]) -> bool:
    """True si la base tiene tablas del Sprint 2 pero nunca se le aplicó la 0002.

    Es el estado en el que quedó QA: `create_all` creó las tablas nuevas, pero
    las columnas y los CHECK de las migraciones no existen.
    """
    return (
        TABLA_ANTERIOR in tablas
        and "tipo_uso" in tablas
        and COLUMNA_SPRINT_2 not in columnas_usuario
    )


def _columnas_usuario(inspector) -> set[str]:
    if TABLA_ANTERIOR not in inspector.get_table_names():
        return set()
    return {columna["name"] for columna in inspector.get_columns(TABLA_ANTERIOR)}


def _adoptar(config: Config, tablas: set[str]) -> None:
    """Elimina las tablas del Sprint 2 y marca el esquema base como baseline."""
    sobrantes = sorted(tablas & TABLAS_POSTERIORES)
    with engine.begin() as conn:
        for nombre in sobrantes:
            conn.execute(text(f'DROP TABLE IF EXISTS "{nombre}" CASCADE'))
    command.stamp(config, REVISION_BASE)
    print(
        "Esquema anterior adoptado: se eliminaron las tablas del Sprint 2 "
        f"({', '.join(sobrantes) or 'ninguna'}) y se marca {REVISION_BASE}."
    )


def migrar() -> bool:
    """Deja el esquema al día. Devuelve True si tuvo que adoptar un esquema viejo."""
    config = Config("alembic.ini")
    inspector = inspect(engine)
    tablas = set(inspector.get_table_names())
    columnas = _columnas_usuario(inspector)

    adoptado = False
    if necesita_adoptar(tablas, columnas):
        _adoptar(config, tablas)
        adoptado = True
    elif esta_contaminada(tablas):
        raise SystemExit(
            "La base tiene tablas del Sprint 2 sin las migraciones aplicadas. "
            "Definir RECREAR_BD=si para recrearla."
        )
    elif es_base_anterior(tablas):
        command.stamp(config, REVISION_BASE)
        print(f"Base existente marcada como {REVISION_BASE}")

    try:
        command.upgrade(config, "head")
    except ProgrammingError as exc:
        if "already exists" in str(exc.orig):
            raise SystemExit(
                "La base quedó a medio migrar: tiene tablas sin la versión de Alembic "
                "que las creó. Definir RECREAR_BD=si para recrearla."
            ) from exc
        raise
    print("Migraciones al día")
    return adoptado


if __name__ == "__main__":
    migrar()
