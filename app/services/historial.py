"""Consulta del historial de acciones (HU-24, SCRUM-88).

Los permisos son los mismos del detalle: si el usuario no puede ver la solicitud
o la reserva, tampoco puede ver su historial.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.modelos import Reserva, Trazabilidad, Usuario
from app.services import reservas, revision
from app.utils.fechas import ZONA_COLOMBIA


def _acciones(db: Session, solicitud_id: int) -> list[dict]:
    filas = db.execute(
        select(Trazabilidad, Usuario)
        .join(Usuario, Usuario.id == Trazabilidad.usuario_id)
        .where(Trazabilidad.solicitud_id == solicitud_id)
        # fecha y luego id: el id desempata si dos acciones tuvieran la misma hora
        .order_by(Trazabilidad.fecha, Trazabilidad.id)
    ).all()
    return [
        {
            "orden": i,
            "accion": t.accion,
            "usuario_id": u.id,
            "usuario_nombre": u.nombre,
            "usuario_rol": u.rol,
            "estado_anterior": t.estado_anterior,
            "estado_nuevo": t.estado_nuevo,
            "detalle": t.detalle,
            "reserva_id": t.reserva_id,
            "fecha": t.fecha.astimezone(ZONA_COLOMBIA),
        }
        for i, (t, u) in enumerate(filas, start=1)
    ]


def de_solicitud(db: Session, usuario: Usuario, solicitud_id: int) -> dict | None:
    if revision.obtener_detalle(db, usuario, solicitud_id) is None:
        return None
    reserva_id = db.scalar(select(Reserva.id).where(Reserva.solicitud_id == solicitud_id))
    return {"solicitud_id": solicitud_id, "reserva_id": reserva_id, "acciones": _acciones(db, solicitud_id)}


def de_reserva(db: Session, usuario: Usuario, reserva_id: int) -> dict | None:
    detalle = reservas.obtener_detalle(db, usuario, reserva_id)
    if detalle is None:
        return None
    solicitud_id = detalle["solicitud_id"]
    return {"solicitud_id": solicitud_id, "reserva_id": reserva_id, "acciones": _acciones(db, solicitud_id)}
