"""Tarea: Backend - endpoint listar espacios y consultar disponibilidad por fecha/horario (HU-01)."""
from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol
from app.core.database import get_db
from app.models.enums import Rol, TipoEspacio
from app.models.modelos import Usuario
from app.schemas.espacio import (
    EspacioActualizar,
    EspacioAdminOut,
    EspacioCrear,
    EspacioEstadoActualizar,
    EspacioMetricaOut,
    EspacioOut,
)
from app.services import disponibilidad, metricas_espacios
from app.services import espacios as gestion_espacios

router = APIRouter()


def _ejecutar(db: Session, accion, *args):
    try:
        return accion(db, *args)
    except gestion_espacios.ErrorEspacio as error:
        db.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from error


@router.post(
    "/",
    response_model=EspacioAdminOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un espacio",
    description=(
        "**HU-19.** Registra un laboratorio o sala. Para ADMIN y APROBADOR. El espacio queda "
        "activo. Si lo crea un APROBADOR, queda asignado como su aprobador; si lo crea un ADMIN, "
        "queda sin aprobadores. El nombre debe ser único."
    ),
    response_description="Espacio creado, con su id",
    responses={
        401: {"description": "No autenticado"},
        403: {"description": "Solo para usuarios ADMIN o APROBADOR"},
        409: {"description": "Ya existe un espacio con ese nombre"},
        422: {"description": "Datos inválidos"},
    },
)
def crear_espacio(
    datos: EspacioCrear,
    usuario: Usuario = Depends(requiere_rol(Rol.ADMIN, Rol.APROBADOR)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, gestion_espacios.crear, usuario, datos)


@router.get(
    "/admin",
    response_model=list[EspacioAdminOut],
    summary="Listar espacios para administración",
    description=(
        "Devuelve espacios activos e inactivos. El ADMIN ve todos; el APROBADOR solo los que "
        "tiene asignados."
    ),
    response_description="Espacios ordenados por tipo y nombre",
    responses={
        401: {"description": "No autenticado"},
        403: {"description": "Solo para usuarios ADMIN o APROBADOR"},
    },
)
def listar_espacios_admin(
    usuario: Usuario = Depends(requiere_rol(Rol.ADMIN, Rol.APROBADOR)),
    db: Session = Depends(get_db),
):
    return gestion_espacios.listar_admin(db, usuario)


@router.patch(
    "/{espacio_id}",
    response_model=EspacioAdminOut,
    summary="Actualizar un espacio",
    description=(
        "Actualiza parcialmente nombre, tipo, capacidad o ubicación. El ADMIN puede editar "
        "cualquier espacio; el APROBADOR solo los que tiene asignados. "
        "No se permite reducir la capacidad por debajo de los asistentes de una reserva futura "
        "ACTIVA. Los campos omitidos no cambian; `ubicacion: null` la quita."
    ),
    response_description="Espacio actualizado",
    responses={
        401: {"description": "No autenticado"},
        403: {"description": "Solo para usuarios ADMIN o APROBADOR"},
        404: {"description": "El espacio no existe o no lo tienes asignado"},
        409: {"description": "Nombre duplicado o capacidad incompatible con una reserva futura"},
        422: {"description": "Datos inválidos"},
    },
)
def actualizar_espacio(
    espacio_id: int,
    datos: EspacioActualizar,
    usuario: Usuario = Depends(requiere_rol(Rol.ADMIN, Rol.APROBADOR)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, gestion_espacios.actualizar, usuario, espacio_id, datos)


@router.patch(
    "/{espacio_id}/estado",
    response_model=EspacioAdminOut,
    summary="Activar o desactivar un espacio",
    description=(
        "Cambia el campo `activo`. Al desactivar se conservan las reservas futuras ya aprobadas, "
        "pero no se permiten nuevas solicitudes ni aprobaciones. No elimina el espacio ni su historial. "
        "El ADMIN puede cambiar cualquier espacio; el APROBADOR solo los que tiene asignados."
    ),
    response_description="Espacio con su nuevo estado",
    responses={
        401: {"description": "No autenticado"},
        403: {"description": "Solo para usuarios ADMIN o APROBADOR"},
        404: {"description": "El espacio no existe o no lo tienes asignado"},
        422: {"description": "Falta el campo activo o es inválido"},
    },
)
def cambiar_estado_espacio(
    espacio_id: int,
    datos: EspacioEstadoActualizar,
    usuario: Usuario = Depends(requiere_rol(Rol.ADMIN, Rol.APROBADOR)),
    db: Session = Depends(get_db),
):
    return _ejecutar(db, gestion_espacios.cambiar_estado, usuario, espacio_id, datos.activo)


@router.get(
    "/metricas",
    response_model=list[EspacioMetricaOut],
    summary="Métricas de reservas por espacio",
    description=(
        "Devuelve en una sola consulta las métricas de los espacios para la fecha indicada. "
        "El ADMIN ve todos; el APROBADOR solo los que tiene asignados. Cuenta reservas ACTIVAS que se cruzan con la fecha; las canceladas no "
        "cuentan. Se reserva todos los días, solo de 07:00 a 22:00: cada espacio activo tiene "
        "900 minutos disponibles por día. Los espacios inactivos tienen 0 minutos disponibles "
        "y porcentaje null."
    ),
    response_description="Métricas por espacio para la fecha consultada",
    responses={
        401: {"description": "No autenticado"},
        403: {"description": "Solo para usuarios ADMIN o APROBADOR"},
    },
)
def metricas_por_espacio(
    fecha: date = Query(..., description="Fecha a consultar (AAAA-MM-DD)", examples=["2026-10-06"]),
    usuario: Usuario = Depends(requiere_rol(Rol.ADMIN, Rol.APROBADOR)),
    db: Session = Depends(get_db),
):
    return metricas_espacios.listar_por_fecha(db, usuario, fecha)


@router.get(
    "/",
    response_model=list[EspacioOut],
    summary="Listar espacios",
    description=(
        "**HU-01.** Devuelve los laboratorios y salas activos. Se puede filtrar por tipo. "
        "Los espacios inactivos no aparecen."
    ),
    response_description="Lista de espacios activos",
)
def listar_espacios(
    tipo: TipoEspacio | None = Query(None, description="Filtrar por LABORATORIO o SALA. Si no se envía, trae ambos."),
    db: Session = Depends(get_db),
):
    return disponibilidad.listar_espacios(db, tipo)


@router.get(
    "/disponibles",
    response_model=list[EspacioOut],
    summary="Consultar espacios disponibles",
    description=(
        "**HU-01.** Devuelve los espacios activos que NO tienen una reserva activa que se cruce "
        "con el horario consultado. Las reservas canceladas no bloquean, y una reserva que termina "
        "justo cuando empieza la consulta tampoco.\n\n"
        "Las horas se interpretan en hora de Colombia (-05:00). "
        "Si no hay espacios disponibles, responde 200 con una lista vacía."
    ),
    response_description="Espacios disponibles en el horario consultado",
    responses={422: {"description": "Faltan parámetros, la hora de fin no es mayor que la de inicio o la fecha ya pasó"}},
)
def consultar_disponibles(
    fecha: date = Query(..., description="Fecha a consultar (AAAA-MM-DD)", examples=["2026-10-05"]),
    hora_inicio: time = Query(..., description="Hora de inicio (HH:MM)", examples=["08:00"]),
    hora_fin: time = Query(..., description="Hora de fin (HH:MM)", examples=["10:00"]),
    tipo: TipoEspacio | None = Query(None, description="Filtrar por LABORATORIO o SALA"),
    db: Session = Depends(get_db),
):
    try:
        inicio, fin = disponibilidad.construir_rango(fecha, hora_inicio, hora_fin)
    except disponibilidad.RangoInvalido as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return disponibilidad.listar_disponibles(db, inicio, fin, tipo)
