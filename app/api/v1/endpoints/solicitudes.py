"""Tareas: SCRUM-73 crear solicitud (HU-04) y SCRUM-75 validar disponibilidad (HU-05)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol
from app.core.database import get_db
from app.models.enums import EstadoSolicitud, Rol
from app.models.modelos import Usuario
from app.schemas.solicitud import SolicitudCreadaOut, SolicitudCrear, SolicitudOut
from app.services import solicitudes

router = APIRouter()

_ERRORES_CREAR = {
    401: {"description": "No autenticado"},
    403: {"description": "Solo los usuarios SOLICITANTE pueden crear solicitudes"},
    404: {"description": "El espacio no existe o no está activo"},
    409: {"description": "El espacio ya está ocupado en ese horario, o ya tienes una solicitud pendiente que se cruza"},
    422: {"description": "Datos inválidos: campos vacíos, horario invertido o pasado, o asistentes por encima de la capacidad"},
}


@router.post(
    "/",
    response_model=SolicitudCreadaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear solicitud de reserva",
    description=(
        "**HU-04 y HU-05.** Registra una solicitud de reserva en estado PENDIENTE y devuelve su "
        "identificador único. Solo para usuarios con rol SOLICITANTE.\n\n"
        "Antes de registrar se valida:\n"
        "- Que el espacio exista y esté activo.\n"
        "- Que el horario sea válido y no esté en el pasado.\n"
        "- Que los asistentes no superen la capacidad del espacio.\n"
        "- Que el espacio no tenga una reserva activa que se cruce (HU-05). Si la tiene, "
        "responde 409 y la solicitud no se registra.\n"
        "- Que el mismo usuario no tenga ya una solicitud pendiente para ese espacio en un "
        "horario que se cruce (evita duplicados por doble clic).\n\n"
        "La creación queda registrada en el historial (acción CREADA)."
    ),
    response_description="Solicitud registrada",
    responses=_ERRORES_CREAR,
)
def crear_solicitud(
    datos: SolicitudCrear,
    usuario: Usuario = Depends(requiere_rol(Rol.SOLICITANTE)),
    db: Session = Depends(get_db),
):
    try:
        resultado = solicitudes.crear(db, usuario, datos)
    except solicitudes.ErrorSolicitud as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from error
    resultado["mensaje"] = f"Solicitud #{resultado['id']} registrada. Quedó en estado PENDIENTE."
    return resultado


@router.get(
    "/mias",
    response_model=list[SolicitudOut],
    summary="Mis solicitudes",
    description=(
        "Devuelve las solicitudes del usuario que inició sesión, de la más reciente a la más "
        "antigua. Incluye el estado y, si fue rechazada, el motivo. Permite al solicitante ver "
        "si su solicitud fue aprobada (HU-10, criterio 6) y el motivo del rechazo (HU-11, criterio 7)."
    ),
    response_description="Solicitudes del usuario",
    responses={401: {"description": "No autenticado"}, 403: {"description": "Solo para usuarios SOLICITANTE"}},
)
def mis_solicitudes(
    estado: EstadoSolicitud | None = Query(None, description="Filtrar por estado"),
    usuario: Usuario = Depends(requiere_rol(Rol.SOLICITANTE)),
    db: Session = Depends(get_db),
):
    return solicitudes.listar_del_usuario(db, usuario, estado)
