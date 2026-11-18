"""Strikes, bloqueo y reactivación de usuarios sancionados (HU-40 y HU-42)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, requiere_rol
from app.core.database import get_db
from app.models.enums import EstadoReactivacion, Rol
from app.models.modelos import Usuario
from app.schemas.sancion import (
    MiEstadoSancionOut,
    ReactivacionCrear,
    ReactivacionDecision,
    ReactivacionOut,
    ReporteSancionesOut,
)
from app.services import asistencia, sanciones

router = APIRouter()

_401 = {401: {"description": "No autenticado"}}
_403 = {403: {"description": "Solo el Administrador del Sistema"}}
_404 = {404: {"description": "La solicitud de reactivación no existe"}}
_409 = {409: {"description": "El usuario no está bloqueado o ya tiene una reactivación pendiente"}}
_422 = {422: {"description": "Datos inválidos"}}


def _ejecutar(db: Session, accion, *args):
    try:
        return accion(db, *args)
    except sanciones.ErrorSancion as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from error


@router.get(
    "/mi-estado",
    response_model=MiEstadoSancionOut,
    summary="Consultar mis strikes y mi estado de bloqueo",
    description=(
        "**HU-40 y HU-42.** Cualquier usuario autenticado consulta sus strikes activos, si está "
        "bloqueado, la política vigente y su reactivación pendiente o última decisión. Antes de "
        "responder se ponen al día los no-show y las advertencias vencidas (HU-39)."
    ),
    response_description="Estado de sanciones del usuario",
    responses={**_401},
)
def mi_estado(
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    asistencia.procesar_vencidas(db)
    return sanciones.estado_usuario(db, usuario)


@router.post(
    "/reactivacion",
    response_model=ReactivacionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Pedir la reactivación estando bloqueado",
    description=(
        "**HU-42.** El usuario bloqueado envía una justificación general y una por cada strike "
        "activo. Debe justificar todos sus strikes y no puede tener otra solicitud pendiente. "
        "Los administradores reciben la solicitud en su campana."
    ),
    response_description="Solicitud de reactivación registrada",
    responses={**_401, **_409, **_422},
)
def pedir_reactivacion(
    datos: ReactivacionCrear,
    usuario: Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    asistencia.procesar_vencidas(db)
    return _ejecutar(db, sanciones.crear_reactivacion, usuario, datos)


@router.get(
    "/reporte",
    response_model=ReporteSancionesOut,
    summary="Reporte de usuarios sancionados",
    description=(
        "**HU-42.** Solo el ADMIN. Lista los usuarios con strikes, su rol, cantidad de strikes "
        "activos y si están bloqueados, con el detalle de cada strike (reserva, fecha y minutos "
        "de retraso). Incluye las reactivaciones pendientes. Con `solo_bloqueados=true` filtra "
        "únicamente a los usuarios bloqueados."
    ),
    response_description="Reporte de sancionados y reactivaciones pendientes",
    responses={**_401, **_403},
)
def reporte(
    solo_bloqueados: bool = Query(False, description="Mostrar solo usuarios bloqueados"),
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    asistencia.procesar_vencidas(db)
    return sanciones.reporte(db, solo_bloqueados)


@router.get(
    "/reactivaciones",
    response_model=list[ReactivacionOut],
    summary="Listar solicitudes de reactivación",
    description=(
        "**HU-42.** Solo el ADMIN. Por defecto devuelve las pendientes; con `estado` se pueden "
        "consultar las aceptadas o rechazadas."
    ),
    response_description="Solicitudes de reactivación",
    responses={**_401, **_403},
)
def listar_reactivaciones(
    estado: EstadoReactivacion | None = Query(None, description="PENDIENTE, ACEPTADA o RECHAZADA"),
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return sanciones.listar_reactivaciones(db, estado)


@router.post(
    "/reactivaciones/{reactivacion_id}/decision",
    response_model=ReactivacionOut,
    summary="Aceptar o rechazar una reactivación",
    description=(
        "**HU-42.** Solo el ADMIN. Para aceptar hay que indicar qué strikes se anulan; el "
        "usuario vuelve a poder solicitar. Para rechazar hay que indicar el motivo. En ambos "
        "casos el usuario recibe una notificación."
    ),
    response_description="Reactivación decidida",
    responses={**_401, **_403, **_404, **_409, **_422},
)
def decidir_reactivacion(
    reactivacion_id: int,
    datos: ReactivacionDecision,
    admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, sanciones.decidir_reactivacion, admin, reactivacion_id, datos)


@router.post(
    "/procesar",
    summary="Procesar advertencias y no-show vencidos",
    description=(
        "**HU-39.** Solo el ADMIN. Envía las advertencias pendientes y marca como no-show las "
        "reservas cuya tolerancia ya venció, generando los strikes correspondientes. La "
        "plataforma también lo hace de forma perezosa al consultar reservas o sanciones."
    ),
    responses={**_401, **_403},
)
def procesar(
    _admin: Usuario = Depends(requiere_rol(Rol.ADMIN)),
    db: Session = Depends(get_db),
):
    return asistencia.procesar_vencidas(db)
