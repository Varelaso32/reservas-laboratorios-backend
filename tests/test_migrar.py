"""Pruebas de las utilidades de arranque (migraciones y recreación de la base)."""

from app.utils.migrar import es_base_anterior
from app.utils.recrear_bd import confirmado, ya_versionada


def test_base_creada_con_crear_tablas_se_marca_como_anterior():
    assert es_base_anterior({"usuario", "espacio", "solicitud"}) is True


def test_base_ya_versionada_no_se_marca():
    assert es_base_anterior({"usuario", "alembic_version"}) is False


def test_base_vacia_se_migra_desde_cero():
    assert es_base_anterior(set()) is False


def test_recrear_exige_confirmacion_explicita():
    assert confirmado(None) is False
    assert confirmado("") is False
    assert confirmado("no") is False
    assert confirmado("si") is True
    assert confirmado(" SI ") is True


def test_recrear_no_toca_una_base_ya_versionada():
    assert ya_versionada({"alembic_version", "usuario"}) is True
    assert ya_versionada({"usuario"}) is False
