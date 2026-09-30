"""Tarea: SCRUM-86 consultar reservas activas por usuario (HU-14)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, requiere_rol
from app.core.database import get_db
from app.models.enums import Rol
from app.models.modelos import Usuario
from app.schemas.reserva import ReservaDetalleOut, ReservaResumenOut
from app.services import reservas

router = APIRouter()

# IMPORTANTE: /mias va antes de /{reserva_id}. Si se invierte el orden,
# FastAPI intenta leer "mias" como un id y responde 422.


@router.get(
    "/mias",
    response_model=list[ReservaResumenOut],
    summary="Mis reservas activas",
    description=(
        "**HU-14.** Devuelve las reservas ACTIVAS del usuario que inició sesión que todavía no "
        "han terminado, ordenadas por fecha y hora de inicio. Cada una trae espacio, fecha, "
        "horario y estado.\n\n"
        "No aparecen las reservas canceladas ni las que ya pasaron. Solo se ven las reservas "
        "propias. Solo para usuarios SOLICITANTE."
    ),
    response_description="Reservas activas del usuario",
    responses={401: {"description": "No autenticado"}, 403: {"description": "Solo para usuarios SOLICITANTE"}},
)
def mis_reservas(
    usuario: Usuario = Depends(requiere_rol(Rol.SOLICITANTE)),
    db: Session = Depends(get_db),
):
    return reservas.listar_activas(db, usuario)


@router.get(
    "/{reserva_id}",
    response_model=ReservaDetalleOut,
    summary="Detalle de una reserva",
    description=(
        "**HU-14, criterio 3.** Devuelve el detalle de una reserva: espacio, horario, estado, "
        "titular, propósito, asistentes, equipamiento y quién la aprobó.\n\n"
        "Quién puede verla:\n"
        "- SOLICITANTE: solo las suyas.\n"
        "- APROBADOR: las de los espacios que administra.\n"
        "- ADMIN: todas.\n\n"
        "Si no existe o el usuario no puede verla, responde 404."
    ),
    response_description="Detalle de la reserva",
    responses={401: {"description": "No autenticado"}, 404: {"description": "La reserva no existe o no tienes acceso a ella"}},
)
def detalle_reserva(
    reserva_id: int,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    detalle = reservas.obtener_detalle(db, usuario, reserva_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail="La reserva no existe o no tienes acceso a ella")
    return detalle
