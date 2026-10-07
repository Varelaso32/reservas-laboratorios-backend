"""Pruebas de las operaciones de /api/v1/reservas."""
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.enums import AccionTrazabilidad, EstadoReserva, EstadoSolicitud, Rol, TipoEspacio
from app.models.modelos import Espacio, Reserva, Solicitud, Trazabilidad
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera


URL = "/api/v1/reservas"


def _crear_reserva(usuario, inicio: datetime):
    with SessionLocal() as db:
        espacio = Espacio(
            nombre=f"Laboratorio de prueba {uuid4().hex}",
            tipo=TipoEspacio.LABORATORIO,
            capacidad=20,
            ubicacion="Bloque A",
        )
        db.add(espacio)
        db.flush()

        solicitud = Solicitud(
            solicitante_id=usuario.id,
            espacio_id=espacio.id,
            inicio=inicio,
            fin=inicio + timedelta(hours=1),
            proposito="Prueba",
            asistentes=2,
            estado=EstadoSolicitud.APROBADA,
            decidido_por=usuario.id,
            fecha_decision=datetime.now(ZONA_COLOMBIA),
        )
        db.add(solicitud)
        db.flush()

        reserva = Reserva(
            solicitud_id=solicitud.id,
            espacio_id=espacio.id,
            usuario_id=usuario.id,
            inicio=solicitud.inicio,
            fin=solicitud.fin,
            estado=EstadoReserva.ACTIVA,
        )
        db.add(reserva)
        db.commit()
        return reserva.id, solicitud.id


def test_solicitante_cancela_reserva_propia_y_registra_historial(client, solicitante):
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(hours=2)
    reserva_id, solicitud_id = _crear_reserva(solicitante, inicio)

    respuesta = client.post(f"{URL}/{reserva_id}/cancelar", headers=cabecera(solicitante))

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "CANCELADA"
    with SessionLocal() as db:
        assert db.get(Reserva, reserva_id).estado == EstadoReserva.CANCELADA
        assert db.get(Solicitud, solicitud_id).estado == EstadoSolicitud.CANCELADA
        acciones = db.scalars(
            select(Trazabilidad).where(Trazabilidad.reserva_id == reserva_id)
        ).all()
    assert len(acciones) == 1
    assert acciones[0].accion == AccionTrazabilidad.CANCELADA


def test_cancelar_reserva_ya_cancelada_es_idempotente(client, solicitante):
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(hours=2)
    reserva_id, _ = _crear_reserva(solicitante, inicio)
    primera = client.post(f"{URL}/{reserva_id}/cancelar", headers=cabecera(solicitante))
    segunda = client.post(f"{URL}/{reserva_id}/cancelar", headers=cabecera(solicitante))

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert segunda.json()["estado"] == "CANCELADA"
    with SessionLocal() as db:
        cantidad = len(db.scalars(
            select(Trazabilidad).where(
                Trazabilidad.reserva_id == reserva_id,
                Trazabilidad.accion == AccionTrazabilidad.CANCELADA,
            )
        ).all())
    assert cantidad == 1


def test_solicitante_no_puede_cancelar_reserva_ajena(client, solicitante, crear_usuario):
    otra_persona = crear_usuario("otra@reservas.test")
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(hours=2)
    reserva_id, _ = _crear_reserva(otra_persona, inicio)

    respuesta = client.post(f"{URL}/{reserva_id}/cancelar", headers=cabecera(solicitante))

    assert respuesta.status_code == 404
    with SessionLocal() as db:
        assert db.get(Reserva, reserva_id).estado == EstadoReserva.ACTIVA
        assert db.scalar(
            select(Trazabilidad.id).where(Trazabilidad.reserva_id == reserva_id)
        ) is None


def test_no_se_puede_cancelar_reserva_que_ya_inicio(client, solicitante):
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=30)
    reserva_id, _ = _crear_reserva(solicitante, inicio)

    respuesta = client.post(f"{URL}/{reserva_id}/cancelar", headers=cabecera(solicitante))

    assert respuesta.status_code == 409
    with SessionLocal() as db:
        assert db.get(Reserva, reserva_id).estado == EstadoReserva.ACTIVA
        assert db.scalar(
            select(Trazabilidad.id).where(Trazabilidad.reserva_id == reserva_id)
        ) is None


def test_solo_solicitante_puede_cancelar_reserva(client, crear_usuario):
    aprobador = crear_usuario("aprobador@reservas.test", Rol.APROBADOR)
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(hours=2)
    reserva_id, _ = _crear_reserva(aprobador, inicio)

    respuesta = client.post(f"{URL}/{reserva_id}/cancelar", headers=cabecera(aprobador))

    assert respuesta.status_code == 403
