"""Tarea: Backend - endpoint listar espacios y consultar disponibilidad por fecha/horario (HU-01)."""
from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enums import TipoEspacio
from app.schemas.espacio import EspacioOut
from app.services import disponibilidad

router = APIRouter()


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
        raise HTTPException(status_code=422, detail=str(error))
    return disponibilidad.listar_disponibles(db, inicio, fin, tipo)
