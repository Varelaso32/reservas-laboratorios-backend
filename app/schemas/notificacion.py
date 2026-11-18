"""Schemas de notificaciones y cesión de cupo (HU-30, HU-31)."""
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import EstadoSolicitud, RolReserva, TipoEspacio, TipoNotificacion


class CesionIn(BaseModel):
    aprobar: bool = Field(description="true para ceder el cupo, false para conservarlo")
    motivo: str | None = Field(
        default=None,
        max_length=500,
        description="Motivo obligatorio cuando el titular decide conservar su cupo",
        examples=["El grupo necesita el laboratorio a esa hora"],
    )

    @field_validator("motivo")
    @classmethod
    def motivo_limpio(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return valor.strip() or None


class SolicitudDetalleOut(BaseModel):
    """Datos de la solicitud que originó el aviso, para decidir sin salir de la campana."""

    solicitud_id: int = Field(description="Solicitud relacionada con el aviso")
    estado: EstadoSolicitud = Field(description="Estado de esa solicitud")
    espacio_id: int = Field(description="Identificador del espacio")
    espacio: str = Field(description="Nombre del espacio")
    tipo_espacio: TipoEspacio = Field(description="LABORATORIO o SALA")
    fecha: date = Field(description="Día del horario, hora de Colombia")
    inicio: datetime = Field(description="Inicio del horario, hora de Colombia")
    fin: datetime = Field(description="Fin del horario, hora de Colombia")
    motivo_urgencia: str | None = Field(description="Motivo de urgencia de quien solicita")
    motivo_rechazo: str | None = Field(description="Motivo del rechazo, si fue rechazada")
    solicitante: str = Field(description="Nombre de quien hizo la solicitud")
    rol_solicitante: RolReserva = Field(description="Rol de reserva de quien hizo la solicitud")


class NotificacionOut(BaseModel):
    id: int = Field(description="Identificador de la notificación")
    tipo: TipoNotificacion = Field(description="Motivo del aviso")
    titulo: str = Field(description="Título corto")
    mensaje: str = Field(description="Texto del aviso")
    solicitud_id: int | None = Field(description="Solicitud relacionada, si aplica")
    leida: bool = Field(description="true si el usuario ya la marcó como leída")
    creada_en: datetime = Field(description="Cuándo se generó, hora de Colombia")
    detalle: SolicitudDetalleOut | None = Field(
        default=None,
        description="Datos de la solicitud cuando el aviso se refiere a una",
    )


class NotificacionesResumenOut(BaseModel):
    no_leidas: int = Field(description="Cantidad de notificaciones sin leer")


class NotificacionesLeidasOut(BaseModel):
    actualizadas: int = Field(description="Cuántas notificaciones se marcaron como leídas")


class CesionOut(BaseModel):
    mensaje: str = Field(description="Resultado de la decisión")
    solicitud: dict = Field(description="Solicitud con su estado nuevo")
