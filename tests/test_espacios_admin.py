"""Pruebas de administración de espacios."""
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.enums import EstadoReserva, EstadoSolicitud, Rol, TipoEspacio
from app.models.modelos import Espacio, Reserva, Solicitud, espacio_aprobador
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera


URL = "/api/v1/espacios"


def _crear_espacio(nombre: str | None = None, capacidad: int = 20, activo: bool = True) -> Espacio:
    with SessionLocal() as db:
        espacio = Espacio(
            nombre=f"{nombre or 'Espacio de prueba'} {uuid4().hex}",
            tipo=TipoEspacio.LABORATORIO,
            capacidad=capacidad,
            ubicacion="Bloque A",
            activo=activo,
        )
        db.add(espacio)
        db.commit()
        return espacio


def _crear_solicitud(
    espacio_id: int,
    solicitante_id: int,
    asistentes: int,
    estado: EstadoSolicitud,
    inicio: datetime,
    decidido_por: int | None = None,
) -> int:
    fin = inicio + timedelta(hours=1)
    with SessionLocal() as db:
        solicitud = Solicitud(
            solicitante_id=solicitante_id,
            espacio_id=espacio_id,
            inicio=inicio,
            fin=fin,
            proposito="Prueba de administración de espacio",
            asistentes=asistentes,
            estado=estado,
            decidido_por=decidido_por,
            fecha_decision=datetime.now(ZONA_COLOMBIA) if decidido_por is not None else None,
        )
        db.add(solicitud)
        db.flush()
        if estado == EstadoSolicitud.APROBADA:
            db.add(
                Reserva(
                    solicitud_id=solicitud.id,
                    espacio_id=espacio_id,
                    usuario_id=solicitante_id,
                    inicio=inicio,
                    fin=fin,
                    estado=EstadoReserva.ACTIVA,
                )
            )
        db.commit()
        return solicitud.id


def test_admin_lista_espacios_activos_e_inactivos(client, admin, solicitante):
    activo = _crear_espacio("Visible activo")
    inactivo = _crear_espacio("Visible inactivo", activo=False)

    respuesta = client.get(f"{URL}/admin", headers=cabecera(admin))

    assert respuesta.status_code == 200
    por_id = {espacio["id"]: espacio for espacio in respuesta.json()}
    assert por_id[activo.id]["activo"] is True
    assert por_id[inactivo.id]["activo"] is False
    assert client.get(f"{URL}/admin", headers=cabecera(solicitante)).status_code == 403


def test_admin_actualiza_campos_editables(client, admin):
    espacio = _crear_espacio()
    nombre_nuevo = f"Sala renovada {uuid4().hex}"

    respuesta = client.patch(
        f"{URL}/{espacio.id}",
        json={"nombre": f"  {nombre_nuevo}  ", "tipo": "SALA", "capacidad": 30, "ubicacion": None},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == nombre_nuevo
    assert cuerpo["tipo"] == "SALA"
    assert cuerpo["capacidad"] == 30
    assert cuerpo["ubicacion"] is None
    assert cuerpo["activo"] is True


def test_nombre_duplicado_devuelve_409(client, admin):
    existente = _crear_espacio("Nombre reservado")
    otro = _crear_espacio("Otro espacio")

    respuesta = client.patch(
        f"{URL}/{otro.id}",
        json={"nombre": existente.nombre},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "Ya existe un espacio con ese nombre"


def test_no_reduce_capacidad_por_debajo_de_reserva_futura(client, admin, solicitante):
    espacio = _crear_espacio(capacidad=20)
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(days=2)
    _crear_solicitud(
        espacio.id,
        solicitante.id,
        asistentes=12,
        estado=EstadoSolicitud.APROBADA,
        inicio=inicio,
        decidido_por=admin.id,
    )

    respuesta = client.patch(
        f"{URL}/{espacio.id}",
        json={"capacidad": 10},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 409
    with SessionLocal() as db:
        assert db.get(Espacio, espacio.id).capacidad == 20


def test_desactivar_conserva_reservas_futuras_y_el_historial(client, admin, solicitante):
    espacio = _crear_espacio()
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(days=2)
    solicitud_id = _crear_solicitud(
        espacio.id,
        solicitante.id,
        asistentes=4,
        estado=EstadoSolicitud.APROBADA,
        inicio=inicio,
        decidido_por=admin.id,
    )
    with SessionLocal() as db:
        reserva_id = db.scalar(select(Reserva.id).where(Reserva.solicitud_id == solicitud_id))

    respuesta = client.patch(
        f"{URL}/{espacio.id}/estado",
        json={"activo": False},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["activo"] is False
    assert all(item["id"] != espacio.id for item in client.get(f"{URL}/").json())
    with SessionLocal() as db:
        assert db.get(Reserva, reserva_id).estado == EstadoReserva.ACTIVA
        assert db.get(Solicitud, solicitud_id).estado == EstadoSolicitud.APROBADA


def test_no_aprueba_solicitud_que_supera_capacidad_actual(client, crear_usuario, solicitante):
    aprobador = crear_usuario("aprobador-capacidad@reservas.test", Rol.APROBADOR)
    espacio = _crear_espacio(capacidad=5)
    with SessionLocal() as db:
        db.execute(
            espacio_aprobador.insert().values(espacio_id=espacio.id, usuario_id=aprobador.id)
        )
        db.commit()
    solicitud_id = _crear_solicitud(
        espacio.id,
        solicitante.id,
        asistentes=8,
        estado=EstadoSolicitud.PENDIENTE,
        inicio=datetime.now(ZONA_COLOMBIA) + timedelta(days=2),
    )

    respuesta = client.post(
        f"/api/v1/solicitudes/{solicitud_id}/aprobar",
        headers=cabecera(aprobador),
    )

    assert respuesta.status_code == 409
    assert "supera la capacidad actual" in respuesta.json()["detail"]
    with SessionLocal() as db:
        assert db.get(Solicitud, solicitud_id).estado == EstadoSolicitud.PENDIENTE
        assert db.scalar(select(Reserva.id).where(Reserva.solicitud_id == solicitud_id)) is None


def test_admin_crea_espacio(client, admin):
    cuerpo = {"nombre": f"  Sala nueva {uuid4().hex}  ", "tipo": "SALA", "capacidad": 12, "ubicacion": " Bloque B "}

    respuesta = client.post(f"{URL}/", json=cuerpo, headers=cabecera(admin))

    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["id"] > 0
    assert datos["nombre"] == cuerpo["nombre"].strip()
    assert datos["ubicacion"] == "Bloque B"
    assert datos["activo"] is True


def test_crear_espacio_con_nombre_duplicado_responde_409(client, admin):
    existente = _crear_espacio("Duplicado")

    respuesta = client.post(
        f"{URL}/",
        json={"nombre": existente.nombre, "tipo": "LABORATORIO", "capacidad": 5},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 409


def test_crear_espacio_valida_datos(client, admin):
    respuesta = client.post(
        f"{URL}/", json={"nombre": "   ", "tipo": "SALA", "capacidad": 0}, headers=cabecera(admin)
    )

    assert respuesta.status_code == 422


def test_solo_admin_crea_espacios(client, solicitante):
    respuesta = client.post(
        f"{URL}/", json={"nombre": "No permitido", "tipo": "SALA", "capacidad": 5}, headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 403
