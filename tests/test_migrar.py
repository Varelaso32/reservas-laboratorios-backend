"""Pruebas de las utilidades de arranque (migraciones y recreación de la base)."""

from app.utils.arranque import recrear_solicitado
from app.utils.migrar import (
    TABLAS_BASE,
    TABLAS_POSTERIORES,
    es_base_anterior,
    esta_contaminada,
    necesita_adoptar,
)
from app.utils.recrear_bd import al_dia, confirmado

BASE = {"usuario", "espacio", "solicitud", "reserva", "trazabilidad"}


def test_base_creada_con_crear_tablas_se_marca_como_anterior():
    assert es_base_anterior(BASE) is True


def test_base_ya_versionada_no_se_marca():
    assert es_base_anterior({*BASE, "alembic_version"}) is False


def test_base_vacia_se_migra_desde_cero():
    assert es_base_anterior(set()) is False


def test_base_con_tablas_del_sprint_2_sin_migraciones_esta_contaminada():
    assert esta_contaminada({*BASE, "tipo_uso"}) is True
    assert esta_contaminada({*BASE, "notificacion"}) is True


def test_se_adopta_la_base_con_tablas_del_sprint_2_sin_la_columna():
    assert necesita_adoptar({*BASE, "tipo_uso"}, set()) is True
    assert necesita_adoptar({*BASE, "tipo_uso", "alembic_version"}, set()) is True


def test_no_se_adopta_una_base_sana_ni_una_vacia():
    assert necesita_adoptar({*BASE, "tipo_uso"}, {"puede_autorizar_especial"}) is False
    assert necesita_adoptar(BASE, set()) is False
    assert necesita_adoptar(set(), set()) is False


def test_las_tablas_base_y_las_posteriores_no_se_solapan():
    assert TABLAS_BASE & TABLAS_POSTERIORES == set()


def test_base_limpia_o_versionada_no_esta_contaminada():
    assert esta_contaminada(BASE) is False
    assert esta_contaminada({*BASE, "tipo_uso", "alembic_version"}) is False
    assert esta_contaminada(set()) is False


def test_recrear_solicitado_acepta_variantes_de_la_variable():
    assert recrear_solicitado("si") is True
    assert recrear_solicitado("Si") is True
    assert recrear_solicitado("SI") is True
    assert recrear_solicitado(" sí ") is True
    assert recrear_solicitado("true") is True
    assert recrear_solicitado("1") is True
    assert recrear_solicitado(None) is False
    assert recrear_solicitado("no") is False


def test_recrear_exige_confirmacion_explicita():
    assert confirmado(None) is False
    assert confirmado("") is False
    assert confirmado("no") is False
    assert confirmado("si") is True
    assert confirmado(" SI ") is True


def test_recrear_solo_se_omite_si_la_base_esta_en_head():
    assert al_dia("0007_amenidades", "0007_amenidades") is True
    assert al_dia("0001_baseline", "0007_amenidades") is False
    assert al_dia(None, "0007_amenidades") is False
