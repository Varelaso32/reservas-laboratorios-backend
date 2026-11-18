"""Pruebas del respaldo y de la adopción de un esquema viejo.

La adopción se prueba contra una base desechable, nunca contra `reservas_test`,
porque implica borrar tablas.
"""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings
from app.core.database import Base, engine
from app.models import modelos  # noqa: F401  (registra las tablas en Base)
from app.utils.migrar import _respaldar, migrar
from app.utils.recrear_bd import version_actual

NOMBRE_BD = "reservas_adopcion_test"


@pytest.fixture
def base_desechable(monkeypatch):
    """Crea una base aparte y apunta Alembic a ella durante la prueba."""
    admin = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{NOMBRE_BD}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{NOMBRE_BD}"'))
    url = engine.url.set(database=NOMBRE_BD).render_as_string(hide_password=False)
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    scratch = create_engine(url)
    yield scratch, Config("alembic.ini")
    scratch.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{NOMBRE_BD}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def tabla_temporal():
    nombre = "tmp_respaldo_prueba"
    respaldo = f"respaldo_{nombre}"
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{nombre}"'))
        conn.execute(text(f'DROP TABLE IF EXISTS "{respaldo}"'))
        conn.execute(text(f'CREATE TABLE "{nombre}" (id serial PRIMARY KEY, dato text)'))
    yield nombre
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{nombre}"'))
        conn.execute(text(f'DROP TABLE IF EXISTS "{respaldo}"'))


def test_una_tabla_vacia_no_se_respalda(tabla_temporal):
    with engine.begin() as conn:
        assert _respaldar(conn, tabla_temporal) is None


def test_una_tabla_con_datos_se_copia(tabla_temporal):
    with engine.begin() as conn:
        conn.execute(text(f'INSERT INTO "{tabla_temporal}" (dato) VALUES (\'hola\')'))
        mensaje = _respaldar(conn, tabla_temporal)
        assert "1 filas" in mensaje
        copiadas = conn.execute(
            text(f'SELECT count(*) FROM "respaldo_{tabla_temporal}"')
        ).scalar()
        assert copiadas == 1


def test_un_respaldo_anterior_no_se_sobrescribe(tabla_temporal):
    with engine.begin() as conn:
        conn.execute(text(f'INSERT INTO "{tabla_temporal}" (dato) VALUES (\'hola\')'))
        conn.execute(text(f'CREATE TABLE "respaldo_{tabla_temporal}" (dato text)'))
        mensaje = _respaldar(conn, tabla_temporal)
        assert "ya existía" in mensaje


def _estado_tipo_qa(scratch, config: Config) -> None:
    """Reproduce la base de QA: versión 0001 y tablas del Sprint 2 por create_all."""
    command.upgrade(config, "0001_baseline")
    Base.metadata.create_all(scratch)
    with scratch.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO usuario (nombre, email, clave_hash, rol, cargo, activo) "
                "VALUES ('Samuel', 'samuel@sim.test', 'x', 'ADMIN', "
                "'ADMINISTRADOR_SISTEMA', true)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO espacio (nombre, tipo, capacidad, ubicacion, activo) "
                "VALUES ('Espacio propio', 'LABORATORIO', 20, 'Bloque Z', true)"
            )
        )
        conn.execute(text("INSERT INTO tipo_uso (nombre) VALUES ('Actividad de QA')"))


def test_la_adopcion_deja_el_esquema_en_head_y_conserva_los_datos(base_desechable):
    scratch, config = base_desechable
    _estado_tipo_qa(scratch, config)

    assert migrar(config=config, motor=scratch) is True

    tablas = set(inspect(scratch).get_table_names())
    assert version_actual(tablas, scratch) == "0007_amenidades"
    columnas = {c["name"] for c in inspect(scratch).get_columns("usuario")}
    assert "puede_autorizar_especial" in columnas
    with scratch.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM usuario")).scalar() == 1
        assert (
            conn.execute(text("SELECT count(*) FROM espacio WHERE nombre = 'Espacio propio'"))
            .scalar()
            == 1
        )
        # La tabla que tenía filas quedó respaldada antes de eliminarla.
        assert conn.execute(text("SELECT count(*) FROM respaldo_tipo_uso")).scalar() == 1


def test_una_base_sin_alembic_version_se_marca_como_baseline_sin_borrar_nada(base_desechable):
    scratch, config = base_desechable
    command.upgrade(config, "0001_baseline")
    with scratch.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO usuario (nombre, email, clave_hash, rol, cargo, activo) "
                "VALUES ('Samuel', 'samuel@sim.test', 'x', 'ADMIN', "
                "'ADMINISTRADOR_SISTEMA', true)"
            )
        )
        conn.execute(text("DROP TABLE alembic_version"))

    assert migrar(config=config, motor=scratch) is False

    tablas = set(inspect(scratch).get_table_names())
    assert version_actual(tablas, scratch) == "0007_amenidades"
    with scratch.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM usuario")).scalar() == 1


def test_una_base_ya_migrada_no_se_vuelve_a_tocar(base_desechable):
    scratch, config = base_desechable

    assert migrar(config=config, motor=scratch) is False
    assert migrar(config=config, motor=scratch) is False

    tablas = set(inspect(scratch).get_table_names())
    assert version_actual(tablas, scratch) == "0007_amenidades"
    assert not [t for t in tablas if t.startswith("respaldo_")]
