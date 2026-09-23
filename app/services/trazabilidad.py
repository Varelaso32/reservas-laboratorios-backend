"""Registro del historial de acciones (HU-24 / SCRUM-88).

Se llama dentro de la misma transacción de la acción: si la acción falla,
el registro tampoco queda. No hace commit; lo hace quien lo llama.
"""
from sqlalchemy.orm import Session

from app.models.enums import AccionTrazabilidad
from app.models.modelos import Trazabilidad


def registrar(
    db: Session,
    *,
    solicitud_id: int,
    usuario_id: int,
    accion: AccionTrazabilidad,
    estado_anterior: str | None = None,
    estado_nuevo: str | None = None,
    detalle: str | None = None,
    reserva_id: int | None = None,
) -> Trazabilidad:
    registro = Trazabilidad(
        solicitud_id=solicitud_id,
        reserva_id=reserva_id,
        usuario_id=usuario_id,
        accion=accion,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        detalle=detalle,
    )
    db.add(registro)
    db.flush()
    return registro
