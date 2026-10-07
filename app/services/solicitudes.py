"""Creación y consulta de solicitudes (HU-04, HU-05)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import AccionTrazabilidad, EstadoSolicitud
from app.models.modelos import Espacio, Solicitud, Usuario
from app.schemas.solicitud import SolicitudCrear
from app.services import disponibilidad, trazabilidad
from app.utils.fechas import HORA_APERTURA, HORA_CIERRE, ZONA_COLOMBIA


class ErrorSolicitud(Exception):
    """Error de negocio con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def a_salida(solicitud: Solicitud, espacio_nombre: str) -> dict:
    def local(fecha):
        return fecha.astimezone(ZONA_COLOMBIA) if fecha else None

    return {
        "id": solicitud.id,
        "espacio_id": solicitud.espacio_id,
        "espacio_nombre": espacio_nombre,
        "inicio": local(solicitud.inicio),
        "fin": local(solicitud.fin),
        "proposito": solicitud.proposito,
        "asistentes": solicitud.asistentes,
        "equipamiento": solicitud.equipamiento,
        "estado": solicitud.estado,
        "motivo_rechazo": solicitud.motivo_rechazo,
        "fecha_decision": local(solicitud.fecha_decision),
        "creada_en": local(solicitud.creada_en),
    }


def crear(db: Session, usuario: Usuario, datos: SolicitudCrear) -> dict:
    # Bloquea la fila del espacio hasta el commit: si llegan dos solicitudes al
    # mismo tiempo (doble clic), la segunda espera y ve la primera.
    espacio = db.scalar(select(Espacio).where(Espacio.id == datos.espacio_id).with_for_update())
    if espacio is None or not espacio.activo:
        raise ErrorSolicitud(404, "El espacio no existe o no está activo")

    inicio = datetime.combine(datos.fecha, datos.hora_inicio, ZONA_COLOMBIA)
    fin = datetime.combine(datos.fecha, datos.hora_fin, ZONA_COLOMBIA)
    if fin <= inicio:
        raise ErrorSolicitud(422, "La hora de fin debe ser mayor que la hora de inicio")
    if datos.hora_inicio < HORA_APERTURA or datos.hora_fin > HORA_CIERRE:
        raise ErrorSolicitud(
            422,
            f"Solo se puede reservar entre las {HORA_APERTURA:%H:%M} y las {HORA_CIERRE:%H:%M}",
        )
    if inicio < datetime.now(ZONA_COLOMBIA):
        raise ErrorSolicitud(422, "No se puede solicitar un espacio en una fecha u hora pasada")

    if datos.asistentes > espacio.capacidad:
        raise ErrorSolicitud(
            422, f"La cantidad de asistentes ({datos.asistentes}) supera la capacidad del espacio ({espacio.capacidad})"
        )

    # HU-05: no se registra la solicitud si el espacio ya tiene una reserva en ese horario
    if not disponibilidad.esta_disponible(db, espacio.id, inicio, fin):
        raise ErrorSolicitud(409, "El espacio ya está ocupado en ese horario")

    duplicada = db.scalar(
        select(Solicitud.id).where(
            Solicitud.solicitante_id == usuario.id,
            Solicitud.espacio_id == espacio.id,
            Solicitud.estado == EstadoSolicitud.PENDIENTE,
            Solicitud.inicio < fin,
            Solicitud.fin > inicio,
        )
    )
    if duplicada:
        raise ErrorSolicitud(
            409, f"Ya tienes una solicitud pendiente (#{duplicada}) para ese espacio en un horario que se cruza"
        )

    solicitud = Solicitud(
        solicitante_id=usuario.id,
        espacio_id=espacio.id,
        inicio=inicio,
        fin=fin,
        proposito=datos.proposito,
        asistentes=datos.asistentes,
        equipamiento=datos.equipamiento,
        estado=EstadoSolicitud.PENDIENTE,
    )
    db.add(solicitud)
    db.flush()

    trazabilidad.registrar(
        db,
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        accion=AccionTrazabilidad.CREADA,
        estado_nuevo=EstadoSolicitud.PENDIENTE.value,
    )
    db.commit()
    db.refresh(solicitud)
    return a_salida(solicitud, espacio.nombre)


def listar_del_usuario(db: Session, usuario: Usuario, estado: EstadoSolicitud | None = None) -> list[dict]:
    consulta = (
        select(Solicitud, Espacio.nombre)
        .join(Espacio, Espacio.id == Solicitud.espacio_id)
        .where(Solicitud.solicitante_id == usuario.id)
    )
    if estado is not None:
        consulta = consulta.where(Solicitud.estado == estado)
    filas = db.execute(consulta.order_by(Solicitud.creada_en.desc(), Solicitud.id.desc())).all()
    return [a_salida(solicitud, nombre) for solicitud, nombre in filas]
