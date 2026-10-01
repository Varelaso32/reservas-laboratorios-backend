from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import Cargo, EstadoSolicitud, TipoEspacio


class SolicitanteResumen(BaseModel):
    id: int = Field(description="Identificador del solicitante")
    nombre: str = Field(description="Nombre del solicitante", examples=["Estudiante de Prueba"])
    email: str = Field(description="Correo del solicitante", examples=["estudiante@reservas.test"])
    cargo: Cargo | None = Field(description="ESTUDIANTE, DOCENTE o ADMINISTRATIVO")


class EspacioResumen(BaseModel):
    id: int = Field(description="Identificador del espacio")
    nombre: str = Field(description="Nombre del espacio", examples=["Laboratorio de Redes"])
    tipo: TipoEspacio = Field(description="LABORATORIO o SALA")
    capacidad: int = Field(description="Capacidad máxima")
    ubicacion: str | None = Field(description="Bloque y piso")


class SolicitudPendienteOut(BaseModel):
    id: int = Field(description="Identificador de la solicitud", examples=[2])
    estado: EstadoSolicitud = Field(description="Siempre PENDIENTE en esta lista")
    solicitante: SolicitanteResumen
    espacio: EspacioResumen
    inicio: datetime = Field(description="Inicio del uso, hora de Colombia")
    fin: datetime = Field(description="Fin del uso, hora de Colombia")
    asistentes: int = Field(description="Cantidad de asistentes")
    creada_en: datetime = Field(description="Cuándo se registró")
    vencida: bool = Field(description="true si la hora de inicio ya pasó: ya no se puede aprobar")


class SolicitudDetalleOut(SolicitudPendienteOut):
    estado: EstadoSolicitud = Field(description="PENDIENTE, APROBADA, RECHAZADA o CANCELADA")
    proposito: str = Field(description="Propósito de la reserva")
    equipamiento: str | None = Field(description="Equipos requeridos, si se registraron")
    motivo_rechazo: str | None = Field(description="Motivo, si fue rechazada")
    decidido_por: str | None = Field(description="Nombre de quien aprobó o rechazó")
    fecha_decision: datetime | None = Field(description="Cuándo se aprobó o rechazó")
