"""Notificaciones internas del usuario.

Cubren la cesión de cupo (HU-31) y el estado de las solicitudes: el solicitante
sabe si su solicitud quedó pendiente, aprobada o rechazada —con el motivo— y
los revisores ven lo que tienen por decidir (HU-10, HU-11, HU-35).

El aviso incluye el detalle de la solicitud (espacio, fecha, horario, quién
solicita y el motivo de urgencia o de rechazo) para decidir sin salir de la
campana.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.core.database import get_db
from app.models.modelos import Usuario
from app.schemas.notificacion import (
    NotificacionesLeidasOut,
    NotificacionesResumenOut,
    NotificacionOut,
)
from app.services import notificaciones

router = APIRouter()

_401 = {401: {"description": "No autenticado"}}


@router.get(
    "/",
    response_model=list[NotificacionOut],
    summary="Mis notificaciones",
    description=(
        "Devuelve las notificaciones del usuario autenticado, de la más reciente a la más "
        "antigua: cesiones de cupo (HU-31), solicitudes por revisar y el resultado de las "
        "solicitudes propias (HU-10, HU-11, HU-35). Las que se refieren a una solicitud traen "
        "su detalle (espacio, fecha, horario, quién solicita y el motivo) para decidir o "
        "enterarse sin salir de la campana."
    ),
    response_description="Notificaciones del usuario",
    responses=_401,
)
def listar_notificaciones(
    solo_no_leidas: bool = Query(False, description="true para devolver solo las no leídas"),
    limite: int = Query(50, ge=1, le=100, description="Cantidad máxima de avisos"),
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    return notificaciones.listar(db, usuario, solo_no_leidas=solo_no_leidas, limite=limite)


@router.get(
    "/resumen",
    response_model=NotificacionesResumenOut,
    summary="Notificaciones sin leer",
    description="Cantidad de notificaciones sin leer, para el contador de la campana.",
    response_description="Contador de no leídas",
    responses=_401,
)
def resumen_notificaciones(
    usuario: Usuario = Depends(get_usuario_actual), db: Session = Depends(get_db)
):
    return {"no_leidas": notificaciones.contar_no_leidas(db, usuario)}


@router.post(
    "/leidas",
    response_model=NotificacionesLeidasOut,
    summary="Marcar todas como leídas",
    description="Marca como leídas todas las notificaciones pendientes del usuario.",
    response_description="Cantidad actualizada",
    responses=_401,
)
def marcar_todas_leidas(
    usuario: Usuario = Depends(get_usuario_actual), db: Session = Depends(get_db)
):
    return {"actualizadas": notificaciones.marcar_todas_leidas(db, usuario)}


@router.post(
    "/{notificacion_id}/leida",
    response_model=NotificacionOut,
    summary="Marcar una notificación como leída",
    description="Solo el dueño de la notificación puede marcarla.",
    response_description="Notificación actualizada",
    responses={**_401, 404: {"description": "La notificación no existe o no es del usuario"}},
)
def marcar_leida(
    notificacion_id: int,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    try:
        return notificaciones.marcar_leida(db, usuario, notificacion_id)
    except notificaciones.ErrorNotificacion as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from error
