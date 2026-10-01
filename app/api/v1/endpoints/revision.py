"""Tareas: SCRUM-77 consultar solicitudes pendientes (HU-08) y SCRUM-79 revisar detalle (HU-09)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, requiere_rol
from app.core.database import get_db
from app.models.enums import Rol
from app.models.modelos import Usuario
from app.schemas.revision import SolicitudDetalleOut, SolicitudPendienteOut
from app.services import revision

router = APIRouter()

# IMPORTANTE: /pendientes va antes de /{solicitud_id}. Si se invierte el orden,
# FastAPI intenta leer "pendientes" como un id y responde 422.


@router.get(
    "/pendientes",
    response_model=list[SolicitudPendienteOut],
    summary="Solicitudes pendientes de mis espacios",
    description=(
        "**HU-08.** Devuelve las solicitudes en estado PENDIENTE de los espacios que administra "
        "el aprobador que inició sesión. No muestra solicitudes de otros espacios.\n\n"
        "Cada solicitud trae solicitante, espacio, fecha y horario. Se ordenan por hora de inicio "
        "(las más próximas primero). El campo `vencida` indica que la hora de inicio ya pasó."
    ),
    response_description="Solicitudes pendientes",
    responses={401: {"description": "No autenticado"}, 403: {"description": "Solo para usuarios APROBADOR"}},
)
def solicitudes_pendientes(
    espacio_id: int | None = Query(None, description="Filtrar por un espacio"),
    usuario: Usuario = Depends(requiere_rol(Rol.APROBADOR)),
    db: Session = Depends(get_db),
):
    return revision.listar_pendientes(db, usuario, espacio_id)


@router.get(
    "/{solicitud_id}",
    response_model=SolicitudDetalleOut,
    summary="Detalle de una solicitud",
    description=(
        "**HU-09.** Devuelve todos los datos de una solicitud: solicitante, espacio, fecha y "
        "horario, asistentes, propósito, equipamiento y, si ya se decidió, quién y cuándo.\n\n"
        "Quién puede verla:\n"
        "- APROBADOR: solo solicitudes de los espacios que administra.\n"
        "- SOLICITANTE: solo las suyas.\n"
        "- ADMIN: todas.\n\n"
        "Si la solicitud no existe o el usuario no puede verla, responde 404 (no se revela si existe)."
    ),
    response_description="Detalle de la solicitud",
    responses={401: {"description": "No autenticado"}, 404: {"description": "La solicitud no existe o no tienes acceso a ella"}},
)
def detalle_solicitud(
    solicitud_id: int,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    detalle = revision.obtener_detalle(db, usuario, solicitud_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail="La solicitud no existe o no tienes acceso a ella")
    return detalle
