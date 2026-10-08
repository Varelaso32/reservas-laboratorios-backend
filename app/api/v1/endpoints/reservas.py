"""Tarea: SCRUM-86 consultar reservas activas por usuario (HU-14) y agenda general."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, requiere_rol
from app.core.database import get_db
from app.models.enums import Rol
from app.models.modelos import Usuario
from app.schemas.reserva import ReservaAgendaOut, ReservaDetalleOut, ReservaResumenOut
from app.services import reservas
from app.utils.fechas import ZONA_COLOMBIA

router = APIRouter()

# IMPORTANTE: /mias va antes de /{reserva_id}. Si se invierte el orden,
# FastAPI intenta leer "mias" como un id y responde 422.

MAX_DIAS_AGENDA = 62


@router.get(
    "/",
    response_model=list[ReservaAgendaOut],
    summary="Agenda de reservas (dashboard y calendario)",
    description=(
        "Devuelve las reservas ACTIVAS que se cruzan con un día o con un rango de días, "
        "ordenadas por hora de inicio. El ADMIN ve todas; el APROBADOR solo las de los espacios "
        "que tiene asignados.\n\n"
        "- `fecha`: un solo día (agenda de hoy).\n"
        "- `fecha_inicio` y `fecha_fin`: un rango inclusivo (semana del calendario), "
        f"de máximo {MAX_DIAS_AGENDA} días.\n"
        "- Sin parámetros de fecha: el día de hoy, hora de Colombia.\n\n"
        "No se puede enviar `fecha` junto con el rango."
    ),
    response_description="Reservas activas del periodo",
    responses={
        401: {"description": "No autenticado"},
        403: {"description": "Solo para usuarios ADMIN o APROBADOR"},
        422: {"description": "Combinación de fechas inválida o rango demasiado largo"},
    },
)
def agenda_reservas(
    fecha: date | None = Query(None, description="Un solo día (AAAA-MM-DD)"),
    fecha_inicio: date | None = Query(None, description="Inicio del rango, inclusivo (AAAA-MM-DD)"),
    fecha_fin: date | None = Query(None, description="Fin del rango, inclusivo (AAAA-MM-DD)"),
    espacio_id: int | None = Query(None, gt=0, description="Filtrar por un espacio"),
    usuario: Usuario = Depends(requiere_rol(Rol.ADMIN, Rol.APROBADOR)),
    db: Session = Depends(get_db),
):
    hay_rango = fecha_inicio is not None or fecha_fin is not None
    if fecha is not None and hay_rango:
        raise HTTPException(status_code=422, detail="Envía fecha o el rango fecha_inicio/fecha_fin, no ambos")
    if hay_rango:
        if fecha_inicio is None or fecha_fin is None:
            raise HTTPException(status_code=422, detail="El rango necesita fecha_inicio y fecha_fin")
        if fecha_inicio > fecha_fin:
            raise HTTPException(status_code=422, detail="fecha_inicio no puede ser posterior a fecha_fin")
        if fecha_fin - fecha_inicio >= timedelta(days=MAX_DIAS_AGENDA):
            raise HTTPException(status_code=422, detail=f"El rango no puede superar {MAX_DIAS_AGENDA} días")
        desde, hasta = fecha_inicio, fecha_fin
    else:
        desde = hasta = fecha or datetime.now(ZONA_COLOMBIA).date()
    return reservas.listar_agenda(db, usuario, desde, hasta, espacio_id)


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
