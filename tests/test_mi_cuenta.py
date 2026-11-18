"""Configuración de la propia cuenta: nombre, correo y restablecimiento de clave.

Cualquier usuario (SOLICITANTE, APROBADOR o ADMIN) puede cambiar sus datos
_sin_ ayuda del administrador.
"""
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.enums import Cargo, Rol
from app.models.modelos import Usuario
from tests.conftest import CLAVE, cabecera

URL = "/api/v1/usuarios/"


def _clave_hash(email: str) -> str:
    with SessionLocal() as db:
        return db.scalar(select(Usuario.clave_hash).where(Usuario.email == email))


def test_cambiar_mi_nombre(client, solicitante):
    respuesta = client.patch(
        f"{URL}mi-cuenta", json={"nombre": "Laura Gómez Restrepo"}, headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Laura Gómez Restrepo"
    assert cuerpo["email"] == solicitante.email
    assert cuerpo["rol"] == "SOLICITANTE"  # el rol no se toca aquí
    with SessionLocal() as db:
        assert db.scalar(select(Usuario.nombre).where(Usuario.id == solicitante.id)) == "Laura Gómez Restrepo"


def test_cambiar_mi_correo(client, solicitante):
    respuesta = client.patch(
        f"{URL}mi-cuenta", json={"email": "  laura.gomez@ECCI.edu.co "}, headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["email"] == "laura.gomez@ecci.edu.co"
    # El token sigue funcionando aunque el correo haya cambiado
    assert client.get("/api/v1/auth/me", headers=cabecera(solicitante)).json()["email"] == "laura.gomez@ecci.edu.co"


def test_no_puede_usar_un_correo_ya_registrado(client, solicitante, crear_usuario):
    crear_usuario("otra@reservas.test")

    respuesta = client.patch(
        f"{URL}mi-cuenta", json={"email": "otra@reservas.test"}, headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 409


def test_no_acepta_campos_prohibidos(client, solicitante):
    respuesta = client.patch(
        f"{URL}mi-cuenta",
        json={"nombre": "Nuevo", "rol": "ADMIN", "cargo": "ADMINISTRADOR_SISTEMA"},
        headers=cabecera(solicitante),
    )

    assert respuesta.status_code == 422
    with SessionLocal() as db:
        usuario = db.get(Usuario, solicitante.id)
        assert usuario.rol == Rol.SOLICITANTE
        assert usuario.cargo == Cargo.ESTUDIANTE


def test_sin_sesion_no_configura(client):
    respuesta = client.patch(f"{URL}mi-cuenta", json={"nombre": "X"})
    assert respuesta.status_code == 401


def test_actualizar_mi_clave_exige_la_actual(client, solicitante):
    equivocada = client.patch(
        f"{URL}mi-cuenta/clave",
        json={"clave_actual": "OtraClave2026*", "clave_nueva": "NuevaClave2026*"},
        headers=cabecera(solicitante),
    )
    sin_actual = client.patch(
        f"{URL}mi-cuenta/clave",
        json={"clave_nueva": "NuevaClave2026*"},
        headers=cabecera(solicitante),
    )

    assert equivocada.status_code == 422
    assert "actual" in equivocada.json()["detail"]
    assert sin_actual.status_code == 422


def test_cambiar_mi_clave_y_iniciar_sesion_con_la_nueva(client, solicitante):
    respuesta = client.patch(
        f"{URL}mi-cuenta/clave",
        json={"clave_actual": CLAVE, "clave_nueva": "NuevaClave2026*"},
        headers=cabecera(solicitante),
    )

    assert respuesta.status_code == 200
    assert "Clave actualizada" in respuesta.json()["mensaje"]

    con_nueva = client.post(
        "/api/v1/auth/login",
        data={"username": solicitante.email, "password": "NuevaClave2026*"},
    )
    con_vieja = client.post(
        "/api/v1/auth/login",
        data={"username": solicitante.email, "password": CLAVE},
    )

    assert con_nueva.status_code == 200
    assert con_vieja.status_code == 401


def test_la_clave_nueva_debe_ser_diferente_y_valida(client, solicitante):
    igual = client.patch(
        f"{URL}mi-cuenta/clave",
        json={"clave_actual": CLAVE, "clave_nueva": CLAVE},
        headers=cabecera(solicitante),
    )
    corta = client.patch(
        f"{URL}mi-cuenta/clave",
        json={"clave_actual": CLAVE, "clave_nueva": "corta"},
        headers=cabecera(solicitante),
    )

    assert igual.status_code == 422
    assert "diferente" in igual.json()["detail"]
    assert corta.status_code == 422


def test_el_admin_tambien_configura_su_cuenta(client, admin):
    nombre = client.patch(
        f"{URL}mi-cuenta", json={"nombre": "Samuel Administrador"}, headers=cabecera(admin)
    )
    clave = client.patch(
        f"{URL}mi-cuenta/clave",
        json={"clave_actual": CLAVE, "clave_nueva": "AdminClave2026*"},
        headers=cabecera(admin),
    )

    assert nombre.status_code == 200
    assert clave.status_code == 200
