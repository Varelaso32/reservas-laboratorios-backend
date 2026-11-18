"""Aplica las migraciones de Alembic al arrancar la API.

Contempla los tres estados posibles de una base:

1. **Vacía**: se migra desde cero.
2. **Anterior a Alembic** (creada con `crear_tablas`, sin `alembic_version`):
   se marca como `0001_baseline` y se aplican las migraciones pendientes.
3. **Anterior con tablas del Sprint 2** (las creó `create_all` sin las columnas
   ni los CHECK de las migraciones, y la base está sin versionar o en el
   baseline): se "adopta" el esquema, es decir, se eliminan solo esas tablas
   nuevas y se aplican las migraciones. Los datos de usuarios, espacios,
   solicitudes, reservas y trazabilidad se conservan, y las tablas nuevas que
   tuvieran filas se copian antes a `respaldo_<tabla>`.

Una base **ya migrada** nunca se adopta: si le falta algo, la verificación del
esquema lo reporta y el arranque falla sin modificar nada.

Es idempotente: correrlo varias veces no cambia nada.

Uso: python -m app.utils.migrar
"""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError

from app.core.database import engine
from app.utils.recrear_bd import version_actual

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


def necesita_adoptar(
    tablas: set[str], columnas_usuario: set[str], version: str | None = None
) -> bool:
    """True si la base tiene tablas del Sprint 2 pero nunca se le aplicó la 0002.

    Es el estado en el que quedó QA: `create_all` creó las tablas nuevas, pero
    las columnas y los CHECK de las migraciones no existen.

    Solo se adopta si la base **nunca se versionó** o está en el baseline. Una
    base ya migrada (aunque le falte una columna) no se toca: eso lo reporta la
    verificación del esquema, para no borrar tablas sanas por error.
    """
    return (
        TABLA_ANTERIOR in tablas
        and "tipo_uso" in tablas
        and COLUMNA_SPRINT_2 not in columnas_usuario
        and version in {None, REVISION_BASE}
    )


def _columnas_usuario(inspector) -> set[str]:
    if TABLA_ANTERIOR not in inspector.get_table_names():
        return set()
    return {columna["name"] for columna in inspector.get_columns(TABLA_ANTERIOR)}


def _respaldar(conn, nombre: str) -> str | None:
    """Copia una tabla con datos a `respaldo_<nombre>` antes de eliminarla.

    Devuelve el texto para el registro, o None si la tabla está vacía o el
    respaldo ya existía (no se sobrescribe un respaldo anterior).
    """
    # Los nombres vienen de TABLAS_POSTERIORES (constante), no de entrada externa.
    filas = conn.execute(text(f'SELECT count(*) FROM "{nombre}"')).scalar() or 0  # noqa: S608
    if not filas:
        return None
    respaldo = f"respaldo_{nombre}"
    existentes = set(inspect(conn).get_table_names())
    if respaldo in existentes:
        return f"{respaldo} ya existía, se conserva ({filas} filas en {nombre} al adoptar)"
    conn.execute(text(f'CREATE TABLE "{respaldo}" AS SELECT * FROM "{nombre}"'))  # noqa: S608
    return f"{respaldo} ({filas} filas)"


def _adoptar(config: Config, tablas: set[str]) -> None:
    """Elimina las tablas del Sprint 2 y marca el esquema base como baseline.

    Las tablas que tengan datos se copian antes a `respaldo_<tabla>`: la
    adopción nunca borra filas sin dejar una copia.
    """
    sobrantes = sorted(tablas & TABLAS_POSTERIORES)
    respaldos: list[str] = []
    with engine.begin() as conn:
        for nombre in sobrantes:
            respaldo = _respaldar(conn, nombre)
            if respaldo:
                respaldos.append(respaldo)
            conn.execute(text(f'DROP TABLE IF EXISTS "{nombre}" CASCADE'))
    command.stamp(config, REVISION_BASE)
    print(
        "Esquema anterior adoptado: se eliminaron las tablas del Sprint 2 "
        f"({', '.join(sobrantes) or 'ninguna'}) y se marca {REVISION_BASE}."
    )
    if respaldos:
        print("Tablas con datos copiadas antes de eliminarlas: " + ", ".join(respaldos))


def migrar() -> bool:
    """Deja el esquema al día. Devuelve True si tuvo que adoptar un esquema viejo."""
    config = Config("alembic.ini")
    inspector = inspect(engine)
    tablas = set(inspector.get_table_names())
    columnas = _columnas_usuario(inspector)
    version = version_actual(tablas)

    adoptado = False
    if necesita_adoptar(tablas, columnas, version):
        _adoptar(config, tablas)
        adoptado = True
    elif es_base_anterior(tablas):
        command.stamp(config, REVISION_BASE)
        print(f"Base existente marcada como {REVISION_BASE}")

    try:
        command.upgrade(config, "head")
    except ProgrammingError as exc:
        if "already exists" in str(exc.orig):
            raise SystemExit(
                "La base quedó a medio migrar: tiene objetos que las migraciones "
                "intentan crear otra vez. Revisar el log; si hay datos que "
                "conservar, restaurarlos desde las tablas respaldo_* antes de "
                "recrear con RECREAR_BD=si y CONFIRMAR_RECREAR_BD=si."
            ) from exc
        raise
    print("Migraciones al día")
    return adoptado


if __name__ == "__main__":
    migrar()
