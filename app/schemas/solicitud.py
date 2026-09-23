from datetime import date, datetime, time

from pydantic import BaseModel, Field, field_validator

from app.models.enums import EstadoSolicitud


class SolicitudCrear(BaseModel):
    espacio_id: int = Field(description="Espacio que se quiere reservar", examples=[2])
    fecha: date = Field(description="Día de uso (AAAA-MM-DD)", examples=["2026-10-05"])
    hora_inicio: time = Field(description="Hora de inicio (HH:MM, hora de Colombia)", examples=["08:00"])
    hora_fin: time = Field(description="Hora de fin (HH:MM, hora de Colombia)", examples=["10:00"])
    proposito: str = Field(min_length=1, max_length=500, description="Para qué se usará el espacio", examples=["Práctica de laboratorio de redes"])
    asistentes: int = Field(gt=0, description="Cantidad de personas", examples=[15])
    equipamiento: str | None = Field(default=None, max_length=500, description="Equipos requeridos (opcional)", examples=["Proyector y 15 computadores"])

    @field_validator("proposito")
    @classmethod
    def proposito_no_vacio(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("El propósito no puede estar vacío")
        return valor

    @field_validator("equipamiento")
    @classmethod
    def equipamiento_limpio(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return valor.strip() or None


class SolicitudOut(BaseModel):
    id: int = Field(description="Identificador único de la solicitud", examples=[12])
    espacio_id: int = Field(description="Identificador del espacio", examples=[2])
    espacio_nombre: str = Field(description="Nombre del espacio", examples=["Laboratorio de Electrónica"])
    inicio: datetime = Field(description="Inicio del uso, hora de Colombia")
    fin: datetime = Field(description="Fin del uso, hora de Colombia")
    proposito: str = Field(description="Propósito de la reserva")
    asistentes: int = Field(description="Cantidad de asistentes")
    equipamiento: str | None = Field(description="Equipos requeridos")
    estado: EstadoSolicitud = Field(description="PENDIENTE, APROBADA, RECHAZADA o CANCELADA")
    motivo_rechazo: str | None = Field(description="Motivo, si fue rechazada")
    fecha_decision: datetime | None = Field(description="Cuándo se aprobó o rechazó")
    creada_en: datetime = Field(description="Cuándo se registró la solicitud")


class SolicitudCreadaOut(SolicitudOut):
    mensaje: str = Field(description="Confirmación para el solicitante", examples=["Solicitud registrada. Quedó en estado PENDIENTE."])


class DisponibilidadOut(BaseModel):
    espacio_id: int = Field(description="Identificador del espacio")
    disponible: bool = Field(description="true si no hay reservas activas que se crucen")
    mensaje: str = Field(description="Explicación para el usuario", examples=["El espacio está disponible en ese horario"])
