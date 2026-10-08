"""Tarea: SCRUM-86 consultar reservas activas por usuario (HU-14)."""
from fastapi import APIRouter, Depends, HTTPException, Query
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
        "Por defecto no aparecen las reservas canceladas; con `incluir_canceladas=true` también "
        "salen, con estado CANCELADA. Las que ya pasaron nunca aparecen. Solo se ven las reservas "
        "propias. Solo para usuarios SOLICITANTE."
    ),
    response_description="Reservas activas del usuario",
    responses={401: {"description": "No autenticado"}, 403: {"description": "Solo para usuarios SOLICITANTE"}},
)
def mis_reservas(
    incluir_canceladas: bool = Query(False, description="true para incluir también las CANCELADAS"),
    usuario: Usuario = Depends(requiere_rol(Rol.SOLICITANTE)),
    db: Session = Depends(get_db),
):
    return reservas.listar_activas(db, usuario, incluir_canceladas)


@router.post(
    "/{reserva_id}/cancelar",
    response_model=ReservaResumenOut,
    summary="Cancelar una reserva propia",
    description=(
        "Cancela una reserva del usuario SOLICITANTE que todavía no haya iniciado. "
        "La reserva y su solicitud quedan en estado CANCELADA, y se registra la acción "
        "en el historial. Si ya estaba cancelada, devuelve su estado actual sin duplicar "
        "el registro de historial. Las reservas que ya iniciaron no se pueden cancelar."
    ),
    response_description="Reserva con estado CANCELADA",
    responses={
        401: {"description": "No autenticado"},
        403: {"description": "Solo para usuarios SOLICITANTE"},
        404: {"description": "La reserva no existe o no te pertenece"},
        409: {"description": "La reserva ya inició o su solicitud asociada no existe"},
    },
)
def cancelar_reserva(
    reserva_id: int,
    usuario: Usuario = Depends(requiere_rol(Rol.SOLICITANTE)),
    db: Session = Depends(get_db),
):
    try:
        return reservas.cancelar(db, usuario, reserva_id)
    except reservas.ErrorReserva as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from error


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
