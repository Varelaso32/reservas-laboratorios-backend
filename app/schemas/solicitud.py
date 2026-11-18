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
    tipo_uso_id: int | None = Field(
        default=None,
        description="Actividad de la reserva, del catálogo del espacio (HU-22, HU-29)",
        examples=[3],
    )
    responsable_id: int | None = Field(
        default=None,
        description="Docente, coordinador o director responsable (HU-32). Obligatorio si el espacio lo exige",
        examples=[4],
    )
    motivo_urgencia: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Motivo por el que se pide un horario ya ocupado (HU-30). Obligatorio cuando quien "
            "solicita tiene mayor jerarquía que el titular del cupo"
        ),
        examples=["El jurado solo puede asistir a esa hora"],
    )

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

    @field_validator("motivo_urgencia")
    @classmethod
    def motivo_urgencia_limpio(cls, valor: str | None) -> str | None:
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
    estado: EstadoSolicitud = Field(
        description="PENDIENTE, PENDIENTE_AUTORIZACION, APROBADA, RECHAZADA, CANCELADA o EN_ESPERA_CESION"
    )
    tipo_uso: str | None = Field(description="Actividad declarada (HU-29)")
    responsable: str | None = Field(description="Nombre del responsable de la actividad (HU-32)")
    fuera_de_franja: bool = Field(
        description="true si el horario no cabe en la franja de operación del espacio"
    )
    motivo_urgencia: str | None = Field(
        default=None, description="Motivo con el que se pidió un cupo ya ocupado (HU-30)"
    )
    motivo_rechazo: str | None = Field(description="Motivo, si fue rechazada")
    fecha_decision: datetime | None = Field(description="Cuándo se aprobó o rechazó")
    creada_en: datetime = Field(description="Cuándo se registró la solicitud")


class SolicitudCreadaOut(SolicitudOut):
    mensaje: str = Field(description="Confirmación para el solicitante", examples=["Solicitud registrada. Quedó en estado PENDIENTE."])
    avisos: list[str] = Field(
        default_factory=list,
        description="Advertencias de las reglas del espacio, por ejemplo la autorización especial",
    )
    titular: str | None = Field(
        default=None,
        description="Nombre del titular del cupo cuando hubo conflicto de jerarquía (HU-30)",
    )


class DisponibilidadOut(BaseModel):
    espacio_id: int = Field(description="Identificador del espacio")
    disponible: bool = Field(description="true si no hay reservas activas ni solicitudes pendientes que se crucen")
    mensaje: str = Field(description="Explicación para el usuario", examples=["El espacio está disponible en ese horario"])
