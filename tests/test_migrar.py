"""Pruebas de las utilidades de arranque (migraciones y recreación de la base)."""

import pytest

from app.utils import arranque
from app.utils.arranque import recrear_solicitado
from app.utils.esquema import problemas_del_esquema, tablas_faltantes
from app.utils.migrar import (
    TABLAS_BASE,
    TABLAS_POSTERIORES,
    es_base_anterior,
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


def test_base_con_tablas_del_sprint_2_sin_migraciones_se_adopta():
    assert necesita_adoptar({*BASE, "tipo_uso"}, set(), None) is True
    assert necesita_adoptar({*BASE, "tipo_uso"}, set(), "0001_baseline") is True


def test_una_base_ya_migrada_nunca_se_adopta_aunque_le_falte_una_columna():
    # Estado de una base sana en head a la que alguien le quitó una columna:
    # hay que reportarlo, no borrar tablas.
    assert necesita_adoptar({*BASE, "tipo_uso"}, set(), "0007_amenidades") is False
    assert necesita_adoptar({*BASE, "tipo_uso"}, set(), "0002_reglas_reserva") is False


def test_no_se_adopta_una_base_sana_ni_una_vacia():
    assert necesita_adoptar({*BASE, "tipo_uso"}, {"puede_autorizar_especial"}, None) is False
    assert necesita_adoptar(BASE, set(), None) is False
    assert necesita_adoptar(set(), set(), None) is False


def test_las_tablas_base_y_las_posteriores_no_se_solapan():
    assert TABLAS_BASE.isdisjoint(TABLAS_POSTERIORES)


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


def test_recrear_no_hace_nada_sin_la_doble_confirmacion(monkeypatch, capsys):
    recreados: list[str] = []
    monkeypatch.setattr(arranque, "recrear", lambda: recreados.append("recreado"))
    monkeypatch.setenv("RECREAR_BD", "si")
    monkeypatch.delenv("CONFIRMAR_RECREAR_BD", raising=False)

    arranque._recrear_si_se_pidio("0001_baseline", "0007_amenidades")
    assert recreados == []
    assert "no se borra nada" in capsys.readouterr().out

    monkeypatch.setenv("CONFIRMAR_RECREAR_BD", "si")
    arranque._recrear_si_se_pidio("0001_baseline", "0007_amenidades")
    assert recreados == ["recreado"]


def test_recrear_no_se_ejecuta_si_la_base_ya_esta_en_head(monkeypatch):
    recreados: list[str] = []
    monkeypatch.setattr(arranque, "recrear", lambda: recreados.append("recreado"))
    monkeypatch.setenv("RECREAR_BD", "si")
    monkeypatch.setenv("CONFIRMAR_RECREAR_BD", "si")

    arranque._recrear_si_se_pidio("0007_amenidades", "0007_amenidades")
    assert recreados == []


def test_el_arranque_falla_si_el_esquema_quedo_incompleto(monkeypatch):
    monkeypatch.setattr(arranque, "verificar", lambda: ["falta la columna X"])
    with pytest.raises(SystemExit) as error:
        arranque._verificar_o_fallar()
    assert "falta la columna X" in str(error.value)


def test_el_arranque_continua_con_el_esquema_completo(monkeypatch):
    monkeypatch.setattr(arranque, "verificar", list)
    arranque._verificar_o_fallar()


def test_preparar_migra_carga_catalogos_y_verifica(monkeypatch, capsys):
    pasos: list[str] = []

    class Inspector:
        def get_table_names(self) -> list[str]:
            return []

    monkeypatch.setattr(arranque, "inspect", lambda motor: Inspector())
    monkeypatch.setattr(arranque, "version_actual", lambda tablas: None)
    monkeypatch.setattr(arranque, "migrar", lambda: pasos.append("migrar") or True)
    monkeypatch.setattr(arranque, "cargar", lambda: pasos.append("cargar"))
    monkeypatch.setattr(arranque, "verificar", list)
    monkeypatch.delenv("RECREAR_BD", raising=False)

    arranque.preparar()

    assert pasos == ["migrar", "cargar"]
    salida = capsys.readouterr().out
    assert "RECREAR_BD=None" in salida
    assert "Esquema verificado" in salida


def test_un_esquema_al_dia_no_tiene_problemas():
    assert problemas_del_esquema("0007_amenidades", "0007_amenidades", [], {}) == []


def test_una_version_atrasada_se_reporta():
    problemas = problemas_del_esquema("0001_baseline", "0007_amenidades", [], {})
    assert len(problemas) == 1
    assert "0001_baseline" in problemas[0]
    assert "0007_amenidades" in problemas[0]


def test_una_base_sin_versionar_se_reporta():
    problemas = problemas_del_esquema(None, "0007_amenidades", [], {})
    assert "ninguna" in problemas[0]


def test_las_tablas_y_columnas_faltantes_se_reportan_por_separado():
    problemas = problemas_del_esquema(
        "0007_amenidades", "0007_amenidades", ["recurso", "strike"], {"usuario": ["activo"]}
    )
    assert len(problemas) == 2
    assert "recurso, strike" in problemas[0]
    assert "usuario le faltan columnas: activo" in problemas[1]


def test_tablas_faltantes_compara_contra_el_modelo():
    esperadas = {"usuario", "espacio"}
    assert tablas_faltantes({"usuario", "espacio"}, esperadas) == []
    assert tablas_faltantes({"usuario"}, esperadas) == ["espacio"]
    assert tablas_faltantes(set(), esperadas) == ["espacio", "usuario"]
