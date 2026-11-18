"""Pruebas del health check /salud.

La base de pruebas se crea con `crear_tablas` (sin `alembic_version`), así que
por defecto el esquema aparece incompleto: eso permite comprobar que el
endpoint avisa en vez de devolver siempre 200.
"""

import pytest

from app import main as main_module


@pytest.fixture(autouse=True)
def sin_cache_de_salud():
    """El resultado bueno se recuerda en el proceso: se limpia entre pruebas."""
    main_module._CACHE_SALUD.update(ok=False, comprobado_en=0.0)
    yield
    main_module._CACHE_SALUD.update(ok=False, comprobado_en=0.0)


def test_la_raiz_sigue_respondiendo(client):
    respuesta = client.get("/")
    assert respuesta.status_code == 200


def test_salud_avisa_si_el_esquema_no_esta_versionado(client):
    respuesta = client.get("/salud")
    assert respuesta.status_code == 503
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "error"
    assert any("ninguna" in problema for problema in cuerpo["problemas"])


def test_salud_responde_200_cuando_el_esquema_esta_al_dia(client, monkeypatch):
    monkeypatch.setattr(main_module, "verificar", list)
    respuesta = client.get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}


def test_salud_responde_503_si_la_base_no_responde(client, monkeypatch):
    def sin_conexion():
        raise RuntimeError("sin conexión")

    monkeypatch.setattr(main_module, "verificar", sin_conexion)
    respuesta = client.get("/salud")
    assert respuesta.status_code == 503
    assert "RuntimeError" in respuesta.json()["detalle"]


def test_salud_reutiliza_el_resultado_bueno_solo_un_minuto(client, monkeypatch):
    monkeypatch.setattr(main_module, "verificar", list)
    assert client.get("/salud").status_code == 200

    monkeypatch.setattr(main_module, "verificar", lambda: ["algo falló"])
    assert client.get("/salud").status_code == 200  # dentro del minuto: cacheado

    main_module._CACHE_SALUD["comprobado_en"] = 0.0  # se "cumplió" el minuto
    assert client.get("/salud").status_code == 503
