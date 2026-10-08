"""Tareas: SCRUM-81 aprobar solicitud (HU-10), SCRUM-85 generar reserva al aprobar (HU-13)
y SCRUM-83 rechazar solicitud con motivo (HU-11)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol
from app.core.database import get_db
from app.models.enums import Rol
from app.models.modelos import Usuario
from app.schemas.decision import AprobacionOut, RechazoIn, RechazoOut
from app.services import decision

router = APIRouter()

_ERRORES = {
    401: {"description": "No autenticado"},
    403: {"description": "Solo para usuarios APROBADOR o ADMIN"},
    404: {"description": "La solicitud no existe o no pertenece a un espacio que administras"},
    409: {"description": "La solicitud ya no está pendiente, está vencida, o el espacio ya fue reservado en ese horario"},
}


@router.post(
    "/{solicitud_id}/aprobar",
    response_model=AprobacionOut,
    summary="Aprobar solicitud y generar la reserva",
    description=(
        "**HU-10 y HU-13.** Aprueba una solicitud PENDIENTE de un espacio que administra el "
        "aprobador y, en la misma operación, genera la reserva ACTIVA a nombre del solicitante.\n\n"
        "Antes de aprobar se valida:\n"
        "- Que la solicitud esté PENDIENTE (si ya se decidió, 409).\n"
        "- Que no esté vencida (si su hora de inicio ya pasó, 409; solo se puede rechazar).\n"
        "- Que el espacio siga activo y libre en ese horario (si otra solicitud ya se aprobó "
        "para ese horario, 409).\n"
        "- Que los asistentes no superen la capacidad actual del espacio (si la capacidad "
        "cambió después de crear la solicitud, 409).\n\n"
        "Queda registrado quién aprobó y cuándo, y la acción APROBADA en el historial. "
        "Una solicitud nunca genera más de una reserva."
    ),
    response_description="Solicitud aprobada y reserva generada",
    responses=_ERRORES,
)
def aprobar_solicitud(
    solicitud_id: int,
    usuario: Usuario = Depends(requiere_rol(Rol.APROBADOR, Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    try:
        return decision.aprobar(db, usuario, solicitud_id)
    except decision.ErrorDecision as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje)


@router.post(
    "/{solicitud_id}/rechazar",
    response_model=RechazoOut,
    summary="Rechazar solicitud con motivo",
    description=(
        "**HU-11.** Rechaza una solicitud PENDIENTE de un espacio que administra el aprobador. "
        "El motivo es obligatorio y el solicitante lo puede consultar en /solicitudes/mias o en "
        "el detalle. Un rechazo no genera reserva. Se puede rechazar aunque esté vencida.\n\n"
        "Queda registrado quién rechazó y cuándo, y la acción RECHAZADA en el historial."
    ),
    response_description="Solicitud rechazada",
    responses={**_ERRORES, 409: {"description": "La solicitud ya no está pendiente"}, 422: {"description": "Falta el motivo o está vacío"}},
)
def rechazar_solicitud(
    solicitud_id: int,
    datos: RechazoIn,
    usuario: Usuario = Depends(requiere_rol(Rol.APROBADOR, Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    try:
        return decision.rechazar(db, usuario, solicitud_id, datos.motivo)
    except decision.ErrorDecision as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje)
