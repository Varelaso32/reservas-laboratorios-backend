"""Tarea: SCRUM-88 registro de trazabilidad (HU-24): consulta del historial."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.core.database import get_db
from app.models.modelos import Usuario
from app.schemas.historial import HistorialOut
from app.services import historial

router = APIRouter()

_DESCRIPCION_COMUN = (
    "Cada acción trae el usuario responsable, la acción, el cambio de estado, el detalle "
    "(por ejemplo el motivo del rechazo) y la fecha y hora. Vienen en orden cronológico, "
    "con el campo `orden` para identificar la secuencia.\n\n"
    "El historial no se puede modificar ni borrar: la base de datos lo impide."
)


@router.get(
    "/solicitudes/{solicitud_id}/historial",
    response_model=HistorialOut,
    summary="Historial de una solicitud",
    description=(
        "**HU-24.** Devuelve la secuencia de acciones registradas sobre una solicitud: "
        "creación, aprobación o rechazo.\n\n"
        + _DESCRIPCION_COMUN
        + "\n\nQuién puede verlo: SOLICITANTE (sus solicitudes), APROBADOR (las de sus "
        "espacios), ADMIN (todas)."
    ),
    response_description="Historial de la solicitud",
    responses={401: {"description": "No autenticado"}, 404: {"description": "La solicitud no existe o no tienes acceso a ella"}},
)
def historial_solicitud(
    solicitud_id: int,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    resultado = historial.de_solicitud(db, usuario, solicitud_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail="La solicitud no existe o no tienes acceso a ella")
    return resultado


@router.get(
    "/reservas/{reserva_id}/historial",
    response_model=HistorialOut,
    summary="Historial de una reserva",
    description=(
        "**HU-24.** Devuelve la secuencia de acciones de la solicitud que generó la reserva, "
        "desde su creación hasta la aprobación.\n\n"
        + _DESCRIPCION_COMUN
        + "\n\nQuién puede verlo: SOLICITANTE (sus reservas), APROBADOR (las de sus "
        "espacios), ADMIN (todas)."
    ),
    response_description="Historial de la reserva",
    responses={401: {"description": "No autenticado"}, 404: {"description": "La reserva no existe o no tienes acceso a ella"}},
)
def historial_reserva(
    reserva_id: int,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    resultado = historial.de_reserva(db, usuario, reserva_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail="La reserva no existe o no tienes acceso a ella")
    return resultado
