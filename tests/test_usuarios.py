"""Pruebas de /api/v1/usuarios."""
import threading

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import verificar_clave
from app.models.enums import Cargo, Rol
from app.models.modelos import Usuario
from app.schemas.usuario import UsuarioCrear
from app.services import usuarios
from app.utils import crear_admin
from tests.conftest import CLAVE, cabecera

URL = "/api/v1/usuarios/"


def _datos(**cambios) -> dict:
    datos = {
        "nombre": "Laura Gómez",
        "email": "laura.gomez@ecci.edu.co",
        "clave": "Laboratorio2026*",
        "rol": "SOLICITANTE",
        "cargo": "ESTUDIANTE",
    }
    datos.update(cambios)
    return datos


def _en_bd(usuario_id: int) -> Usuario | None:
    with SessionLocal() as db:
        return db.get(Usuario, usuario_id)


# ---------- Crear ----------

def test_crear_usuario_valido(client, admin):
    r = client.post(URL, json=_datos(), headers=cabecera(admin))
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["email"] == "laura.gomez@ecci.edu.co"
    assert cuerpo["rol"] == "SOLICITANTE"
    assert cuerpo["activo"] is True
    assert "clave" not in cuerpo and "clave_hash" not in cuerpo


def test_la_clave_se_guarda_como_hash(client, admin):
    r = client.post(URL, json=_datos(), headers=cabecera(admin))
    guardado = _en_bd(r.json()["id"])
    assert guardado.clave_hash != "Laboratorio2026*"
    assert guardado.clave_hash.startswith("$argon2")
    assert verificar_clave("Laboratorio2026*", guardado.clave_hash)


def test_crear_normaliza_correo_y_nombre(client, admin):
    r = client.post(URL, json=_datos(email="  Laura.Gomez@ECCI.edu.co ", nombre="  Laura  "), headers=cabecera(admin))
    assert r.status_code == 201
    assert r.json()["email"] == "laura.gomez@ecci.edu.co"
    assert r.json()["nombre"] == "Laura"


def test_crear_acepta_dominio_test(client, admin):
    r = client.post(URL, json=_datos(email="nuevo@reservas.test"), headers=cabecera(admin))
    assert r.status_code == 201


def test_correo_duplicado_409(client, admin):
    assert client.post(URL, json=_datos(), headers=cabecera(admin)).status_code == 201
    r = client.post(URL, json=_datos(email="laura.gomez@ecci.edu.co"), headers=cabecera(admin))
    assert r.status_code == 409


def test_correo_duplicado_con_mayusculas_y_espacios_409(client, admin):
    assert client.post(URL, json=_datos(email="juan@x.com"), headers=cabecera(admin)).status_code == 201
    r = client.post(URL, json=_datos(email="  JUAN@X.com "), headers=cabecera(admin))
    assert r.status_code == 409
    assert r.json() == {"detail": "Ya existe un usuario con ese correo"}


def test_correo_duplicado_en_simultaneo(admin):
    """Dos creaciones al mismo tiempo con el mismo correo: una entra y la otra da 409, nunca 500."""
    barrera = threading.Barrier(2)
    resultados = []

    def crear(email):
        datos = UsuarioCrear(**_datos(email=email))
        barrera.wait()
        with SessionLocal() as db:
            try:
                resultados.append(usuarios.crear(db, datos).id)
            except usuarios.ErrorUsuario as error:
                db.rollback()
                resultados.append(error.codigo)

    hilos = [threading.Thread(target=crear, args=(e,)) for e in ("carrera@x.com", "CARRERA@x.com")]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert 409 in resultados
    assert len(resultados) == 2
    with SessionLocal() as db:
        assert len(db.scalars(select(Usuario).where(Usuario.email == "carrera@x.com")).all()) == 1


def test_rol_invalido_422(client, admin):
    r = client.post(URL, json=_datos(rol="SUPERADMIN"), headers=cabecera(admin))
    assert r.status_code == 422


@pytest.mark.parametrize("clave", ["corta", "1234567", "x" * 129])
def test_clave_fuera_de_rango_422(client, admin, clave):
    r = client.post(URL, json=_datos(clave=clave), headers=cabecera(admin))
    assert r.status_code == 422


@pytest.mark.parametrize(
    "email",
    ["no-es-correo", "a@@x.com", "a@b@x.com", "@x.com", "juan@", "juan@localhost", "ju an@x.com",
     "juan@.com", "juan@x.", "a" * 250 + "@x.com"],
)
def test_correo_invalido_422(client, admin, email):
    r = client.post(URL, json=_datos(email=email), headers=cabecera(admin))
    assert r.status_code == 422


@pytest.mark.parametrize("nombre", ["", "   ", "n" * 121])
def test_nombre_invalido_422(client, admin, nombre):
    r = client.post(URL, json=_datos(nombre=nombre), headers=cabecera(admin))
    assert r.status_code == 422


def test_no_acepta_campos_extra(client, admin):
    r = client.post(URL, json=_datos(clave_hash="$argon2id$falso", activo=False), headers=cabecera(admin))
    assert r.status_code == 422


def test_cargo_incoherente_con_rol_400(client, admin):
    r = client.post(URL, json=_datos(rol="SOLICITANTE", cargo="COORDINADOR_LABORATORIOS"), headers=cabecera(admin))
    assert r.status_code == 400


def test_crear_sin_token_401(client):
    assert client.post(URL, json=_datos()).status_code == 401


def test_crear_sin_ser_admin_403(client, solicitante):
    r = client.post(URL, json=_datos(rol="ADMIN", cargo="ADMINISTRADOR_SISTEMA"), headers=cabecera(solicitante))
    assert r.status_code == 403


def test_swagger_no_expone_clave_hash(client):
    esquema = client.get("/api/v1/openapi.json").text
    assert "clave_hash" not in esquema


# ---------- Listar ----------

def test_listar_pagina_y_filtra(client, admin, crear_usuario):
    crear_usuario("a@x.com")
    crear_usuario("b@x.com", activo=False)
    crear_usuario("c@x.com", Rol.APROBADOR, Cargo.ADMINISTRADOR_SALA)

    r = client.get(URL, params={"skip": 1, "limit": 2}, headers=cabecera(admin))
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] == 4
    assert [u["email"] for u in cuerpo["items"]] == ["a@x.com", "b@x.com"]

    r = client.get(URL, params={"rol": "SOLICITANTE", "activo": True}, headers=cabecera(admin))
    assert [u["email"] for u in r.json()["items"]] == ["a@x.com"]
    assert all("clave_hash" not in u for u in r.json()["items"])


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"skip": -1}])
def test_listar_paginacion_invalida_422(client, admin, params):
    assert client.get(URL, params=params, headers=cabecera(admin)).status_code == 422


def test_listar_sin_ser_admin_403(client, solicitante):
    assert client.get(URL, headers=cabecera(solicitante)).status_code == 403


# ---------- Consultar ----------

def test_consultar_admin_ve_cualquiera(client, admin, solicitante):
    r = client.get(f"{URL}{solicitante.id}", headers=cabecera(admin))
    assert r.status_code == 200
    assert r.json()["email"] == solicitante.email


def test_consultar_se_ve_a_si_mismo(client, solicitante):
    assert client.get(f"{URL}{solicitante.id}", headers=cabecera(solicitante)).status_code == 200


def test_consultar_otro_sin_ser_admin_404(client, admin, solicitante):
    # 404 y no 403: no se revela si el id existe
    r = client.get(f"{URL}{admin.id}", headers=cabecera(solicitante))
    assert r.status_code == 404
    r_inexistente = client.get(f"{URL}9999", headers=cabecera(solicitante))
    assert r.json() == r_inexistente.json()


def test_consultar_inexistente_404(client, admin):
    assert client.get(f"{URL}9999", headers=cabecera(admin)).status_code == 404


def test_consultar_sin_token_401(client, solicitante):
    assert client.get(f"{URL}{solicitante.id}").status_code == 401


# ---------- Actualizar ----------

def test_actualizar_rol_y_cargo(client, admin, solicitante):
    r = client.patch(
        f"{URL}{solicitante.id}", json={"rol": "APROBADOR", "cargo": "COORDINADOR_LABORATORIOS"},
        headers=cabecera(admin),
    )
    assert r.status_code == 200
    assert r.json()["rol"] == "APROBADOR"
    assert r.json()["email"] == solicitante.email


def test_actualizar_solo_rol_con_cargo_incoherente_400(client, admin, solicitante):
    # El estudiante pasa a APROBADOR pero su cargo sigue siendo ESTUDIANTE
    r = client.patch(f"{URL}{solicitante.id}", json={"rol": "APROBADOR"}, headers=cabecera(admin))
    assert r.status_code == 400
    assert _en_bd(solicitante.id).rol == Rol.SOLICITANTE


def test_actualizar_correo_duplicado_409(client, admin, solicitante):
    r = client.patch(f"{URL}{solicitante.id}", json={"email": " ADMIN@reservas.test"}, headers=cabecera(admin))
    assert r.status_code == 409


def test_actualizar_null_en_campo_obligatorio_422(client, admin, solicitante):
    r = client.patch(f"{URL}{solicitante.id}", json={"nombre": None}, headers=cabecera(admin))
    assert r.status_code == 422


def test_actualizar_inexistente_404(client, admin):
    assert client.patch(f"{URL}9999", json={"nombre": "X"}, headers=cabecera(admin)).status_code == 404


def test_actualizar_sin_ser_admin_403(client, solicitante):
    r = client.patch(
        f"{URL}{solicitante.id}", json={"rol": "ADMIN", "cargo": "ADMINISTRADOR_SISTEMA"},
        headers=cabecera(solicitante),
    )
    assert r.status_code == 403
    assert _en_bd(solicitante.id).rol == Rol.SOLICITANTE


def test_no_se_quita_el_rol_al_unico_admin_400(client, admin):
    r = client.patch(f"{URL}{admin.id}", json={"rol": "SOLICITANTE", "cargo": None}, headers=cabecera(admin))
    assert r.status_code == 400
    assert _en_bd(admin.id).rol == Rol.ADMIN


# ---------- Estado ----------

def test_desactivar_es_borrado_logico(client, admin, solicitante):
    r = client.patch(f"{URL}{solicitante.id}/estado", json={"activo": False}, headers=cabecera(admin))
    assert r.status_code == 200
    assert r.json()["activo"] is False

    guardado = _en_bd(solicitante.id)
    assert guardado is not None
    assert guardado.activo is False

    # Su token deja de servir y no puede volver a iniciar sesión
    assert client.get("/api/v1/auth/me", headers=cabecera(solicitante)).status_code == 401
    login = client.post("/api/v1/auth/login", data={"username": solicitante.email, "password": CLAVE})
    assert login.status_code == 403


def test_reactivar_usuario(client, admin, crear_usuario):
    inactivo = crear_usuario("inactivo@x.com", activo=False)
    r = client.patch(f"{URL}{inactivo.id}/estado", json={"activo": True}, headers=cabecera(admin))
    assert r.status_code == 200
    assert _en_bd(inactivo.id).activo is True


def test_no_se_desactiva_al_unico_admin_400(client, admin):
    r = client.patch(f"{URL}{admin.id}/estado", json={"activo": False}, headers=cabecera(admin))
    assert r.status_code == 400
    assert _en_bd(admin.id).activo is True


def test_con_dos_admins_si_se_puede_desactivar_uno(client, admin, crear_usuario):
    otro = crear_usuario("otro.admin@x.com", Rol.ADMIN, Cargo.ADMINISTRADOR_SISTEMA)
    r = client.patch(f"{URL}{otro.id}/estado", json={"activo": False}, headers=cabecera(admin))
    assert r.status_code == 200


def test_estado_sin_ser_admin_403(client, admin, solicitante):
    r = client.patch(f"{URL}{admin.id}/estado", json={"activo": False}, headers=cabecera(solicitante))
    assert r.status_code == 403


# ---------- Script del primer admin ----------

def test_script_crear_admin(client, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_EMAIL", " Primer.Admin@ECCI.edu.co")
    monkeypatch.setenv("ADMIN_NOMBRE", "Primer Admin")
    monkeypatch.setenv("ADMIN_CLAVE", "ClaveInicial2026*")

    assert crear_admin.crear_admin() == 0
    assert crear_admin.crear_admin() == 0  # la segunda vez no duplica
    assert "Ya existe" in capsys.readouterr().out

    with SessionLocal() as db:
        admins = db.scalars(select(Usuario).where(Usuario.rol == Rol.ADMIN)).all()
    assert [a.email for a in admins] == ["primer.admin@ecci.edu.co"]

    login = client.post("/api/v1/auth/login", data={"username": "primer.admin@ecci.edu.co", "password": "ClaveInicial2026*"})
    assert login.status_code == 200


def test_script_crear_admin_sin_variables(monkeypatch):
    for v in ("ADMIN_EMAIL", "ADMIN_NOMBRE", "ADMIN_CLAVE"):
        monkeypatch.delenv(v, raising=False)
    assert crear_admin.crear_admin() == 1
