"""Consulta de reservas (HU-14)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.models.enums import EstadoReserva, Rol
from app.models.modelos import Espacio, Reserva, Solicitud, Usuario
from app.services.revision import gestiona_espacio
from app.utils.fechas import ZONA_COLOMBIA

Titular = aliased(Usuario)
Aprobador = aliased(Usuario)


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


def listar_activas(db: Session, usuario: Usuario) -> list[dict]:
    """HU-14: reservas ACTIVAS del usuario que todavía no han terminado.

    Las canceladas no aparecen (criterio 5) y las que ya pasaron tampoco.
    """
    ahora = datetime.now(ZONA_COLOMBIA)
    filas = db.execute(
        select(Reserva, Espacio)
        .join(Espacio, Espacio.id == Reserva.espacio_id)
        .where(
            Reserva.usuario_id == usuario.id,
            Reserva.estado == EstadoReserva.ACTIVA,
            Reserva.fin > ahora,
        )
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
