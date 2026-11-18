"""Tareas: SCRUM-73 crear solicitud (HU-04) y SCRUM-75 validar disponibilidad (HU-05).

Aquí también viven las reglas de reserva (HU-21, HU-28 a HU-35) y la bandeja de
autorización especial (HU-35).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, requiere_rol
from app.core.database import get_db
from app.models.enums import EstadoSolicitud, Rol
from app.models.modelos import Usuario
from app.schemas.configuracion import AutorizacionIn, AutorizacionOut
from app.schemas.notificacion import CesionIn, CesionOut
from app.schemas.solicitud import SolicitudCreadaOut, SolicitudCrear, SolicitudOut
from app.services import autorizacion, cesion, solicitudes

router = APIRouter()

_ERRORES_CREAR = {
    401: {"description": "No autenticado"},
    403: {"description": "Solo los usuarios SOLICITANTE pueden crear solicitudes"},
    404: {"description": "El espacio no existe o no está activo"},
    409: {
        "description": (
            "El espacio ya está ocupado en ese horario, ya existe una solicitud pendiente "
            "(de cualquier usuario) que se cruza, el espacio alcanzó su máximo de usos del día "
            "o no se respeta la separación entre reservas"
        )
    },
    422: {
        "description": (
            "Datos inválidos o regla del espacio incumplida: horario fuera de la franja de "
            "operación, asistentes fuera de capacidad u ocupación mínima, actividad no permitida, "
            "anticipación excedida, duración por encima del máximo o falta el responsable"
        )
    },
}


@router.post(
    "/",
    response_model=SolicitudCreadaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear solicitud de reserva",
    description=(
        "**HU-04 y HU-05.** Registra una solicitud de reserva y devuelve su identificador "
        "único. Solo para usuarios con rol SOLICITANTE.\n\n"
        "Antes de registrar se valida, en este orden:\n"
        "- Que el espacio exista y esté activo.\n"
        "- Que el horario sea válido y no esté en el pasado.\n"
        "- Que el espacio no tenga una reserva activa que se cruce (HU-05). Si la tiene, "
        "responde 409 y la solicitud no se registra.\n"
        "- Que el mismo usuario no tenga ya una solicitud pendiente para ese espacio en un "
        "horario que se cruce (evita duplicados por doble clic).\n"
        "- **HU-21 y HU-34:** que el horario esté dentro de la franja de operación y de los días "
        "operables del espacio. Si está fuera y el espacio admite autorización especial (HU-35), "
        "la solicitud queda en estado PENDIENTE_AUTORIZACION.\n"
        "- **HU-28:** que los asistentes no superen la capacidad ni queden por debajo de la "
        "ocupación mínima del espacio.\n"
        "- **HU-29:** que la actividad esté entre las configuradas para el espacio.\n"
        "- **HU-32:** que la fecha respete la anticipación máxima del rol y que, si el espacio "
        "exige responsable, se envíe uno con nivel Docente, Coordinador o Director.\n"
        "- **HU-33:** que la duración no supere la máxima y que se respete la separación entre "
        "reservas.\n"
        "- **HU-34:** que el espacio no haya alcanzado su máximo de usos de ese día.\n\n"
        "- **HU-30:** si el horario coincide con el cupo vigente de otro usuario, se resuelve por "
        "jerarquía de rol. Con el mismo rol o uno inferior, la solicitud se rechaza automáticamente "
        "y se guarda en estado RECHAZADA con el motivo. Con un rol superior y un "
        "`motivo_urgencia`, queda en estado EN_ESPERA_CESION a la espera de la decisión del "
        "titular (HU-31).\n\n"
        "La creación queda registrada en el historial (acción CREADA, y CONFLICTO_RECHAZADO o "
        "CESION_SOLICITADA cuando hubo conflicto de cupo)."
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
    resultado["mensaje"] = (
        f"Solicitud #{resultado['id']} registrada. Quedó en estado {resultado['estado'].value}."
    )
    return resultado


@router.get(
    "/mias",
    response_model=list[SolicitudOut],
    summary="Mis solicitudes",
    description=(
        "Devuelve las solicitudes del usuario que inició sesión, de la más reciente a la más "
        "antigua. Incluye el estado, la actividad, el responsable y, si fue rechazada, el motivo. "
        "Permite al solicitante ver si su solicitud fue aprobada (HU-10, criterio 6) y el motivo "
        "del rechazo (HU-11, criterio 7)."
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


@router.get(
    "/autorizaciones",
    summary="Solicitudes pendientes de autorización especial",
    description=(
        "**HU-35.** Devuelve las solicitudes que quedaron fuera de la franja de operación y "
        "esperan autorización especial, con el rol de quien solicita, el espacio, la fecha, el "
        "horario y el motivo de urgencia. Solo para usuarios con permiso de autorización especial."
    ),
    response_description="Solicitudes en estado PENDIENTE_AUTORIZACION",
    responses={
        401: {"description": "No autenticado"},
        403: {"description": "El usuario no tiene permiso de autorización especial"},
    },
)
def listar_autorizaciones(
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    try:
        return autorizacion.listar_pendientes(db, usuario)
    except autorizacion.ErrorAutorizacion as error:
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from error


@router.post(
    "/{solicitud_id}/autorizacion",
    response_model=AutorizacionOut,
    summary="Autorizar o negar una solicitud fuera de la franja",
    description=(
        "**HU-35.** Solo para usuarios con permiso de autorización especial.\n\n"
        "- Con `aprobar: true` la solicitud vuelve a PENDIENTE y sigue el flujo normal de "
        "aprobación (HU-10). Si el horario ya fue reservado, responde 409.\n"
        "- Con `aprobar: false` pasa a RECHAZADA y el motivo es obligatorio.\n\n"
        "La decisión queda en la trazabilidad (acción AUTORIZADA o AUTORIZACION_DENEGADA)."
    ),
    response_description="Solicitud con su estado nuevo",
    responses={
        401: {"description": "No autenticado"},
        403: {"description": "El usuario no tiene permiso de autorización especial"},
        404: {"description": "La solicitud no existe"},
        409: {"description": "La solicitud ya no espera autorización, está vencida o el horario ya fue reservado"},
        422: {"description": "Se negó la autorización sin motivo"},
    },
)
def decidir_autorizacion(
    solicitud_id: int,
    datos: AutorizacionIn,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    try:
        return autorizacion.decidir(db, usuario, solicitud_id, datos.aprobar, datos.motivo)
    except autorizacion.ErrorAutorizacion as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from error


@router.post(
    "/{solicitud_id}/cesion",
    response_model=CesionOut,
    summary="Ceder o conservar el cupo (HU-31)",
    description=(
        "**HU-31.** Solo el titular del cupo puede decidir sobre una solicitud en estado "
        "EN_ESPERA_CESION.\n\n"
        "- Con `aprobar: true` el cupo del titular se libera y la reserva pasa a nombre de quien "
        "solicitó. La solicitud queda APROBADA y se crea la reserva.\n"
        "- Con `aprobar: false` la solicitud queda RECHAZADA y el motivo es obligatorio. El "
        "titular conserva su cupo.\n\n"
        "Ambas partes reciben una notificación y la decisión queda en la trazabilidad "
        "(acción CESION_ACEPTADA o CESION_RECHAZADA)."
    ),
    response_description="Solicitud con su estado nuevo",
    responses={
        401: {"description": "No autenticado"},
        403: {"description": "El usuario no es el titular del cupo"},
        404: {"description": "La solicitud no existe"},
        409: {
            "description": (
                "La solicitud ya no espera cesión, está vencida o el horario ya fue reservado por "
                "otra solicitud aprobada"
            )
        },
        422: {"description": "Se intentó conservar el cupo sin indicar motivo"},
    },
)
def decidir_cesion(
    solicitud_id: int,
    datos: CesionIn,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    try:
        return cesion.decidir(db, usuario, solicitud_id, datos.aprobar, datos.motivo)
    except cesion.ErrorCesion as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from error
