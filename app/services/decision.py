"""Aprobar y rechazar solicitudes (HU-10, HU-11, HU-13).

Aprobar es una sola transacción: cambia el estado, crea la reserva y registra el
historial. Si algo falla, no queda nada a medias.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import AccionTrazabilidad, EstadoReserva, EstadoSolicitud, Rol
from app.models.modelos import Espacio, Reserva, Solicitud, Usuario
from app.services import disponibilidad, revision, trazabilidad
from app.utils.fechas import ZONA_COLOMBIA


class ErrorDecision(Exception):
    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _tomar_pendiente(db: Session, aprobador: Usuario, solicitud_id: int) -> Solicitud:
    # FOR UPDATE: si dos aprobadores actúan sobre la misma solicitud a la vez,
    # el segundo espera y luego ve el estado ya cambiado.
    solicitud = db.scalar(select(Solicitud).where(Solicitud.id == solicitud_id).with_for_update())
    no_encontrada = ErrorDecision(404, "La solicitud no existe o no tienes acceso a ella")
    if solicitud is None:
        raise no_encontrada
    # El ADMIN decide en cualquier espacio; el APROBADOR solo en los asignados
    if aprobador.rol != Rol.ADMIN and not db.scalar(
        select(revision.gestiona_espacio(solicitud.espacio_id, aprobador.id))
    ):
        raise no_encontrada
    if solicitud.estado != EstadoSolicitud.PENDIENTE:
        raise ErrorDecision(409, f"La solicitud ya no está pendiente (estado actual: {solicitud.estado.value})")
    return solicitud


def aprobar(db: Session, aprobador: Usuario, solicitud_id: int) -> dict:
    solicitud = _tomar_pendiente(db, aprobador, solicitud_id)
    ahora = datetime.now(ZONA_COLOMBIA)

    if solicitud.inicio < ahora:
        raise ErrorDecision(409, "La solicitud está vencida: su hora de inicio ya pasó. Solo se puede rechazar")

    espacio = db.scalar(
        select(Espacio).where(Espacio.id == solicitud.espacio_id).with_for_update()
    )
    if not espacio.activo:
        raise ErrorDecision(409, "El espacio ya no está activo. Solo se puede rechazar")
    if solicitud.asistentes > espacio.capacidad:
        raise ErrorDecision(
            409,
            "La cantidad de asistentes supera la capacidad actual del espacio. La solicitud no se puede aprobar",
        )

    # Se revalida: otra solicitud del mismo horario pudo aprobarse después de creada esta
    if not disponibilidad.esta_disponible(db, solicitud.espacio_id, solicitud.inicio, solicitud.fin):
        raise ErrorDecision(409, "El espacio ya fue reservado en ese horario por otra solicitud aprobada")

    estado_anterior = solicitud.estado.value
    solicitud.estado = EstadoSolicitud.APROBADA
    solicitud.decidido_por = aprobador.id
    solicitud.fecha_decision = ahora

    # HU-13: la reserva conserva espacio, fecha y horario, y queda a nombre del solicitante
    reserva = Reserva(
        solicitud_id=solicitud.id,
        espacio_id=solicitud.espacio_id,
        usuario_id=solicitud.solicitante_id,
        inicio=solicitud.inicio,
        fin=solicitud.fin,
        estado=EstadoReserva.ACTIVA,
    )
    db.add(reserva)
    try:
        db.flush()
    except IntegrityError as error:
        # Dos aprobaciones simultáneas del mismo horario: la BD deja pasar solo una
        if "ex_reserva_sin_cruce" in str(error.orig):
            raise ErrorDecision(409, "El espacio ya fue reservado en ese horario por otra solicitud aprobada") from error
        raise

    trazabilidad.registrar(
        db,
        solicitud_id=solicitud.id,
        reserva_id=reserva.id,
        usuario_id=aprobador.id,
        accion=AccionTrazabilidad.APROBADA,
        estado_anterior=estado_anterior,
        estado_nuevo=EstadoSolicitud.APROBADA.value,
        detalle=f"Reserva #{reserva.id} generada",
    )
    db.commit()

    return {
        "mensaje": f"Solicitud #{solicitud.id} aprobada. Se generó la reserva #{reserva.id}.",
        "solicitud": revision.obtener_detalle(db, aprobador, solicitud.id),
        "reserva": {
            "id": reserva.id,
            "solicitud_id": solicitud.id,
            "espacio_id": espacio.id,
            "espacio_nombre": espacio.nombre,
            "inicio": reserva.inicio.astimezone(ZONA_COLOMBIA),
            "fin": reserva.fin.astimezone(ZONA_COLOMBIA),
            "estado": reserva.estado,
        },
    }


def rechazar(db: Session, aprobador: Usuario, solicitud_id: int, motivo: str) -> dict:
    solicitud = _tomar_pendiente(db, aprobador, solicitud_id)
    estado_anterior = solicitud.estado.value

    # HU-11: se puede rechazar aunque esté vencida; un rechazo nunca genera reserva
    solicitud.estado = EstadoSolicitud.RECHAZADA
    solicitud.motivo_rechazo = motivo
    solicitud.decidido_por = aprobador.id
    solicitud.fecha_decision = datetime.now(ZONA_COLOMBIA)

    trazabilidad.registrar(
        db,
        solicitud_id=solicitud.id,
        usuario_id=aprobador.id,
        accion=AccionTrazabilidad.RECHAZADA,
        estado_anterior=estado_anterior,
        estado_nuevo=EstadoSolicitud.RECHAZADA.value,
        detalle=motivo,
    )
    db.commit()

    return {
        "mensaje": f"Solicitud #{solicitud.id} rechazada.",
        "solicitud": revision.obtener_detalle(db, aprobador, solicitud.id),
    }
