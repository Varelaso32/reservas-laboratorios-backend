"""Tarea SCRUM-75 (HU-05): validar la disponibilidad de un espacio antes de solicitar."""
from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.modelos import Espacio
from app.schemas.solicitud import DisponibilidadOut
from app.services import disponibilidad

router = APIRouter()


@router.get(
    "/{espacio_id}/disponibilidad",
    response_model=DisponibilidadOut,
    summary="Validar disponibilidad de un espacio",
    description=(
        "**HU-05.** Indica si un espacio está libre en un horario, para que el frontend pueda "
        "avisar antes de enviar la solicitud. Es solo informativo: al crear la solicitud la "
        "disponibilidad se vuelve a validar."
    ),
    response_description="Resultado de la validación",
    responses={
        404: {"description": "El espacio no existe o no está activo"},
        422: {"description": "Horario inválido o en el pasado"},
    },
)
def validar_disponibilidad(
    espacio_id: int,
    fecha: date = Query(..., description="Fecha (AAAA-MM-DD)", examples=["2026-10-05"]),
    hora_inicio: time = Query(..., description="Hora de inicio (HH:MM)", examples=["08:00"]),
    hora_fin: time = Query(..., description="Hora de fin (HH:MM)", examples=["10:00"]),
    db: Session = Depends(get_db),
):
    espacio = db.get(Espacio, espacio_id)
    if espacio is None or not espacio.activo:
        raise HTTPException(status_code=404, detail="El espacio no existe o no está activo")
    try:
        inicio, fin = disponibilidad.construir_rango(fecha, hora_inicio, hora_fin)
    except disponibilidad.RangoInvalido as error:
        raise HTTPException(status_code=422, detail=str(error))
    libre = disponibilidad.esta_disponible(db, espacio_id, inicio, fin)
    mensaje = "El espacio está disponible en ese horario" if libre else "El espacio ya se encuentra ocupado en ese horario"
    return DisponibilidadOut(espacio_id=espacio_id, disponible=libre, mensaje=mensaje)
