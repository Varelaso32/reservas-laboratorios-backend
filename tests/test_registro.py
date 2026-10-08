"""Pruebas de POST /api/v1/auth/registro."""
import pytest

from app.core.database import SessionLocal
from app.models.modelos import Usuario
from tests.conftest import cabecera

URL = "/api/v1/auth/registro"


def _datos(**cambios) -> dict:
    datos = {"nombre": "Laura Gómez", "email": "laura.gomez@ecci.edu.co", "clave": "Laboratorio2026*"}
    datos.update(cambios)
    return datos


def test_registro_crea_estudiante_sin_token(client):
    r = client.post(URL, json=_datos())
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["rol"] == "SOLICITANTE"
    assert cuerpo["cargo"] == "ESTUDIANTE"
    assert cuerpo["activo"] is True
    assert "clave" not in cuerpo and "clave_hash" not in cuerpo
    assert "access_token" not in cuerpo  # opción A: no inicia sesión


def test_registro_luego_puede_iniciar_sesion(client):
    client.post(URL, json=_datos())
    login = client.post("/api/v1/auth/login", data={"username": "laura.gomez@ecci.edu.co", "password": "Laboratorio2026*"})
    assert login.status_code == 200
    assert login.json()["usuario"]["rol"] == "SOLICITANTE"


def test_registro_guarda_hash(client):
    r = client.post(URL, json=_datos())
    with SessionLocal() as db:
        guardado = db.get(Usuario, r.json()["id"])
    assert guardado.clave_hash.startswith("$argon2")


def test_registro_acepta_reservas_test(client):
    assert client.post(URL, json=_datos(email="nuevo@reservas.test")).status_code == 201


def test_registro_normaliza_correo(client):
    r = client.post(URL, json=_datos(email="  Laura.Gomez@ECCI.EDU.CO "))
    assert r.status_code == 201
    assert r.json()["email"] == "laura.gomez@ecci.edu.co"


@pytest.mark.parametrize(
    "email",
    ["laura@gmail.com", "laura@ecci.edu.co.evil.com", "laura@falso-ecci.edu.co", "laura@est.ecci.edu.co", "laura@ecci.edu"],
)
def test_registro_rechaza_otros_dominios_400(client, email):
    r = client.post(URL, json=_datos(email=email))
    assert r.status_code == 400
    assert "institucionales" in r.json()["detail"]


@pytest.mark.parametrize(
    "extra",
    [{"rol": "ADMIN"}, {"rol": "SOLICITANTE"}, {"cargo": "ADMINISTRADOR_SISTEMA"}, {"activo": False}, {"clave_hash": "x"}],
)
def test_registro_no_permite_elegir_rol_ni_otros_campos_422(client, extra):
    r = client.post(URL, json=_datos(**extra))
    assert r.status_code == 422
    with SessionLocal() as db:
        assert db.query(Usuario).count() == 0


def test_registro_correo_duplicado_409(client):
    assert client.post(URL, json=_datos()).status_code == 201
    assert client.post(URL, json=_datos(email=" LAURA.GOMEZ@ecci.edu.co")).status_code == 409


def test_registro_duplicado_de_usuario_creado_por_admin_409(client, admin):
    # admin@reservas.test ya existe (lo creó la fixture)
    assert client.post(URL, json=_datos(email="admin@reservas.test")).status_code == 409


@pytest.mark.parametrize("cambios", [{"clave": "corta"}, {"nombre": "  "}, {"email": "no-es-correo"}])
def test_registro_datos_invalidos_422(client, cambios):
    assert client.post(URL, json=_datos(**cambios)).status_code == 422


def test_registro_con_token_de_admin_igual_crea_estudiante(client, admin):
    # El endpoint ignora la sesión: aunque llame un ADMIN, la cuenta nace SOLICITANTE
    r = client.post(URL, json=_datos(), headers=cabecera(admin))
    assert r.status_code == 201
    assert r.json()["rol"] == "SOLICITANTE"
