"""Pruebas de la verificación del esquema (app/utils/esquema.py)."""

from sqlalchemy import create_engine

from app.utils.esquema import (
    columnas_faltantes,
    problemas_del_esquema,
    revision_head,
    tablas_faltantes,
    verificar,
)


class InspectorFalso:
    """Inspector mínimo: solo lo que usa `columnas_faltantes`."""

    def __init__(self, columnas: dict[str, list[str]]) -> None:
        self.columnas = columnas

    def get_columns(self, tabla: str) -> list[dict]:
        return [{"name": nombre} for nombre in self.columnas.get(tabla, [])]


def test_revision_head_devuelve_la_ultima_migracion():
    head = revision_head()
    assert isinstance(head, str)
    assert head


def test_la_base_de_pruebas_solo_falla_por_el_versionado():
    # crear_tablas deja todas las tablas y columnas, pero sin alembic_version.
    problemas = verificar()
    assert len(problemas) == 1
    assert "ninguna" in problemas[0]


def test_una_base_vacia_reporta_tablas_faltantes_y_version():
    problemas = verificar(create_engine("sqlite://"))
    assert any("Faltan tablas" in problema for problema in problemas)
    assert any("ninguna" in problema for problema in problemas)


def test_columnas_faltantes_detecta_las_que_no_estan():
    inspector = InspectorFalso({"usuario": ["id", "nombre"]})
    faltan = columnas_faltantes(inspector, {"usuario"})
    assert "email" in faltan["usuario"]
    assert "id" not in faltan["usuario"]


def test_columnas_faltantes_ignora_tablas_que_no_existen():
    assert columnas_faltantes(InspectorFalso({}), {"inventada"}) == {}


def test_una_base_sin_tablas_del_modelo_no_tiene_columnas_faltantes():
    assert tablas_faltantes(set()) != []
    assert columnas_faltantes(InspectorFalso({}), set()) == {}


def test_sin_problemas_cuando_la_version_y_las_tablas_coinciden():
    assert problemas_del_esquema("0007_amenidades", "0007_amenidades", [], {}) == []
