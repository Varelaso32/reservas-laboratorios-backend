from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import EstadoReserva
from app.schemas.revision import SolicitudDetalleOut


class RechazoIn(BaseModel):
    motivo: str = Field(min_length=1, max_length=500, description="Por qué se rechaza. Obligatorio", examples=["El laboratorio está en mantenimiento esa semana"])

    @field_validator("motivo")
    @classmethod
    def motivo_no_vacio(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("El motivo del rechazo no puede estar vacío")
        return valor


class ReservaOut(BaseModel):
    id: int = Field(description="Identificador de la reserva", examples=[3])
    solicitud_id: int = Field(description="Solicitud que la generó")
    espacio_id: int = Field(description="Espacio reservado")
    espacio_nombre: str = Field(description="Nombre del espacio")
    inicio: datetime = Field(description="Inicio, hora de Colombia")
    fin: datetime = Field(description="Fin, hora de Colombia")
    estado: EstadoReserva = Field(description="ACTIVA al crearse")


class AprobacionOut(BaseModel):
    mensaje: str = Field(description="Confirmación", examples=["Solicitud #2 aprobada. Se generó la reserva #3."])
    solicitud: SolicitudDetalleOut
    reserva: ReservaOut


class RechazoOut(BaseModel):
    mensaje: str = Field(description="Confirmación", examples=["Solicitud #3 rechazada."])
    solicitud: SolicitudDetalleOut
