"""Crea las tablas en PostgreSQL. Se puede correr varias veces sin problema.

Uso: docker compose exec api python -m app.utils.crear_tablas
"""
from sqlalchemy import text

from app.core.database import Base, engine
from app.models import modelos  # noqa: F401  (registra las tablas)

BLOQUEAR_CAMBIOS = """
CREATE OR REPLACE FUNCTION trazabilidad_bloquear_cambios() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'La trazabilidad no se puede modificar ni eliminar';
END;
$$ LANGUAGE plpgsql
"""


def crear_tablas() -> None:
    with engine.begin() as conn:
        # Necesaria para la restricción que impide reservas cruzadas
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))

    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        # El historial solo admite inserciones (HU-24)
        conn.execute(text(BLOQUEAR_CAMBIOS))
        conn.execute(text("DROP TRIGGER IF EXISTS trazabilidad_solo_insercion ON trazabilidad"))
        conn.execute(text(
            "CREATE TRIGGER trazabilidad_solo_insercion BEFORE UPDATE OR DELETE ON trazabilidad "
            "FOR EACH ROW EXECUTE FUNCTION trazabilidad_bloquear_cambios()"
        ))


if __name__ == "__main__":
    crear_tablas()
    print("Tablas creadas: " + ", ".join(sorted(Base.metadata.tables)))
