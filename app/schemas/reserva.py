from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import EstadoReserva
from app.schemas.revision import EspacioResumen


class ReservaResumenOut(BaseModel):
    id: int = Field(description="Identificador de la reserva", examples=[2])
    estado: EstadoReserva = Field(description="ACTIVA o CANCELADA")
    espacio: EspacioResumen
    inicio: datetime = Field(description="Inicio, hora de Colombia")
    fin: datetime = Field(description="Fin, hora de Colombia")
    solicitud_id: int = Field(description="Solicitud que generó la reserva")


class ReservaAgendaOut(ReservaResumenOut):
    titular: str = Field(description="Nombre del usuario a cuyo nombre está la reserva")
    proposito: str = Field(description="Propósito registrado en la solicitud")
    asistentes: int = Field(description="Cantidad de asistentes")


class ReservaDetalleOut(ReservaResumenOut):
    finalizada: bool = Field(description="true si la hora de fin ya pasó")
    titular: str = Field(description="Nombre del usuario a cuyo nombre está la reserva")
    proposito: str = Field(description="Propósito registrado en la solicitud")
    asistentes: int = Field(description="Cantidad de asistentes")
    equipamiento: str | None = Field(description="Equipos requeridos")
    aprobada_por: str | None = Field(description="Nombre de quien aprobó la solicitud")
    fecha_aprobacion: datetime | None = Field(description="Cuándo se aprobó")
    creada_en: datetime = Field(description="Cuándo se generó la reserva")
