from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AccionTrazabilidad, Rol


class AccionHistorialOut(BaseModel):
    orden: int = Field(description="Posición en la secuencia: 1 es la primera acción", examples=[1])
    accion: AccionTrazabilidad = Field(description="CREADA, APROBADA, RECHAZADA o CANCELADA")
    usuario_id: int = Field(description="Usuario responsable de la acción")
    usuario_nombre: str = Field(description="Nombre del usuario responsable", examples=["Coordinador de Laboratorios"])
    usuario_rol: Rol = Field(description="Rol del usuario responsable")
    estado_anterior: str | None = Field(description="Estado de la solicitud antes de la acción")
    estado_nuevo: str | None = Field(description="Estado de la solicitud después de la acción")
    detalle: str | None = Field(description="Motivo del rechazo, reserva generada, etc.")
    reserva_id: int | None = Field(description="Reserva relacionada con la acción, si la hay")
    fecha: datetime = Field(description="Fecha y hora de la acción, hora de Colombia")


class HistorialOut(BaseModel):
    solicitud_id: int = Field(description="Solicitud a la que pertenece el historial")
    reserva_id: int | None = Field(description="Reserva generada por la solicitud, si existe")
    acciones: list[AccionHistorialOut] = Field(description="Acciones en orden cronológico")
