"""Consulta de reservas (HU-14)."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.models.enums import AccionTrazabilidad, EstadoReserva, EstadoSolicitud, Rol
from app.models.modelos import Espacio, Reserva, Solicitud, Usuario
from app.services.revision import gestiona_espacio
from app.services import trazabilidad
from app.utils.fechas import ZONA_COLOMBIA

Titular = aliased(Usuario)
Aprobador = aliased(Usuario)


class ErrorReserva(Exception):
    """Error de negocio con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _local(fecha):
    return fecha.astimezone(ZONA_COLOMBIA) if fecha else None


def _resumen(reserva: Reserva, espacio: Espacio) -> dict:
    return {
        "id": reserva.id,
        "estado": reserva.estado,
        "espacio": {
            "id": espacio.id,
            "nombre": espacio.nombre,
            "tipo": espacio.tipo,
            "capacidad": espacio.capacidad,
            "ubicacion": espacio.ubicacion,
        },
        "inicio": _local(reserva.inicio),
        "fin": _local(reserva.fin),
        "solicitud_id": reserva.solicitud_id,
    }


def cancelar(db: Session, usuario: Usuario, reserva_id: int) -> dict:
    """Cancela una reserva propia que todavía no ha comenzado.

    La operación es idempotente: una reserva ya cancelada se devuelve sin crear
    otra acción de historial.
    """
    reserva = db.scalar(
        select(Reserva).where(Reserva.id == reserva_id).with_for_update()
    )
    if reserva is None or reserva.usuario_id != usuario.id:
        raise ErrorReserva(404, "La reserva no existe o no tienes acceso a ella")

    espacio = db.get(Espacio, reserva.espacio_id)
    if reserva.estado == EstadoReserva.CANCELADA:
        return _resumen(reserva, espacio)

    if reserva.inicio <= datetime.now(ZONA_COLOMBIA):
        raise ErrorReserva(409, "No se puede cancelar una reserva que ya inició")

    solicitud = db.scalar(
        select(Solicitud).where(Solicitud.id == reserva.solicitud_id).with_for_update()
    )
    if solicitud is None:
        raise ErrorReserva(409, "La solicitud asociada a la reserva no existe")

    reserva.estado = EstadoReserva.CANCELADA
    solicitud.estado = EstadoSolicitud.CANCELADA
    trazabilidad.registrar(
        db,
        solicitud_id=solicitud.id,
        reserva_id=reserva.id,
        usuario_id=usuario.id,
        accion=AccionTrazabilidad.CANCELADA,
        estado_anterior=EstadoSolicitud.APROBADA.value,
        estado_nuevo=EstadoSolicitud.CANCELADA.value,
        detalle=f"Reserva #{reserva.id} cancelada por el solicitante",
    )
    db.commit()
    return _resumen(reserva, espacio)


def listar_agenda(
    db: Session,
    usuario: Usuario,
    desde: date,
    hasta: date,
    espacio_id: int | None = None,
) -> list[dict]:
    """Reservas ACTIVAS que se cruzan con los días [desde, hasta], hora de Colombia.

    El ADMIN ve todas; el APROBADOR solo las de los espacios que tiene asignados.
    """
    inicio = datetime.combine(desde, time.min, ZONA_COLOMBIA)
    fin = datetime.combine(hasta + timedelta(days=1), time.min, ZONA_COLOMBIA)
    consulta = (
        select(Reserva, Espacio, Solicitud, Titular.nombre)
        .join(Espacio, Espacio.id == Reserva.espacio_id)
        .join(Solicitud, Solicitud.id == Reserva.solicitud_id)
        .join(Titular, Titular.id == Reserva.usuario_id)
        .where(
            Reserva.estado == EstadoReserva.ACTIVA,
            Reserva.inicio < fin,
            Reserva.fin > inicio,
        )
    )
    if usuario.rol != Rol.ADMIN:
        consulta = consulta.where(gestiona_espacio(Reserva.espacio_id, usuario.id))
    if espacio_id is not None:
        consulta = consulta.where(Reserva.espacio_id == espacio_id)

    filas = db.execute(consulta.order_by(Reserva.inicio, Reserva.espacio_id, Reserva.id)).all()
    salida = []
    for reserva, espacio, solicitud, titular in filas:
        item = _resumen(reserva, espacio)
        item.update(
            {"titular": titular, "proposito": solicitud.proposito, "asistentes": solicitud.asistentes}
        )
        salida.append(item)
    return salida


def listar_activas(db: Session, usuario: Usuario, incluir_canceladas: bool = False) -> list[dict]:
    """HU-14: reservas del usuario que todavía no han terminado.

    Por defecto solo las ACTIVAS (criterio 5). Con incluir_canceladas también
    salen las CANCELADAS, para que el dashboard las muestre atenuadas.
    Las que ya pasaron nunca aparecen.
    """
    ahora = datetime.now(ZONA_COLOMBIA)
    filtros = [Reserva.usuario_id == usuario.id, Reserva.fin > ahora]
    if not incluir_canceladas:
        filtros.append(Reserva.estado == EstadoReserva.ACTIVA)
    filas = db.execute(
        select(Reserva, Espacio)
        .join(Espacio, Espacio.id == Reserva.espacio_id)
        .where(*filtros)
        .order_by(Reserva.inicio, Reserva.id)
    ).all()
    return [_resumen(r, e) for r, e in filas]


def obtener_detalle(db: Session, usuario: Usuario, reserva_id: int) -> dict | None:
    """None si no existe o si el usuario no puede verla (no se revela que existe)."""
    fila = db.execute(
        select(Reserva, Espacio, Solicitud, Titular.nombre, Aprobador.nombre)
        .join(Espacio, Espacio.id == Reserva.espacio_id)
        .join(Solicitud, Solicitud.id == Reserva.solicitud_id)
        .join(Titular, Titular.id == Reserva.usuario_id)
        .outerjoin(Aprobador, Aprobador.id == Solicitud.decidido_por)
        .where(Reserva.id == reserva_id)
    ).first()
    if fila is None:
        return None
    reserva, espacio, solicitud, titular, aprobador = fila

    if usuario.rol == Rol.ADMIN:
        permitido = True
    elif usuario.rol == Rol.APROBADOR:
        permitido = bool(db.scalar(select(gestiona_espacio(reserva.espacio_id, usuario.id))))
    else:
        permitido = reserva.usuario_id == usuario.id
    if not permitido:
        return None

    salida = _resumen(reserva, espacio)
    salida.update(
        {
            "finalizada": reserva.fin <= datetime.now(ZONA_COLOMBIA),
            "titular": titular,
            "proposito": solicitud.proposito,
            "asistentes": solicitud.asistentes,
            "equipamiento": solicitud.equipamiento,
            "aprobada_por": aprobador,
            "fecha_aprobacion": _local(solicitud.fecha_decision),
            "creada_en": _local(reserva.creada_en),
        }
    )
    return salida
