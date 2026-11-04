from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import EstadoAsistencia, EstadoReserva
from app.schemas.revision import EspacioResumen


class CancelacionIn(BaseModel):
    """HU-17: el solicitante explica por qué cancela su reserva."""

    motivo: str = Field(
        min_length=5,
        max_length=500,
        description="Motivo de la cancelación; queda asociado a la reserva",
        examples=["Ya no puedo asistir por una clase extraordinaria"],
    )

    @field_validator("motivo")
    @classmethod
    def motivo_limpio(cls, valor: str) -> str:
        valor = valor.strip()
        if len(valor) < 5:
            raise ValueError("El motivo debe tener al menos 5 caracteres")
        return valor


class ReservaResumenOut(BaseModel):
    id: int = Field(description="Identificador de la reserva", examples=[2])
    estado: EstadoReserva = Field(description="ACTIVA, CANCELADA o NO_ASISTIO")
    espacio: EspacioResumen
    inicio: datetime = Field(description="Inicio, hora de Colombia")
    fin: datetime = Field(description="Fin, hora de Colombia")
    solicitud_id: int = Field(description="Solicitud que generó la reserva")
    estado_asistencia: EstadoAsistencia = Field(
        default=EstadoAsistencia.PENDIENTE,
        description="PENDIENTE, ASISTIO o NO_ASISTIO (HU-38)",
    )
    inicio_efectivo: datetime | None = Field(
        default=None, description="Hora real en que se registró la asistencia"
    )
    tolerancia_hasta: datetime | None = Field(
        default=None, description="Último momento para registrar asistencia (HU-39)"
    )
    puede_registrar_asistencia: bool = Field(
        default=False, description="true si el titular puede registrar la asistencia ahora"
    )
    motivo_cancelacion: str | None = Field(
        default=None, description="Motivo registrado al cancelar (HU-17)"
    )


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
