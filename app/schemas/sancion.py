"""Esquemas de asistencia, strikes, sanciones y reactivación (HU-38 a HU-42)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import EstadoReactivacion


class AccionNivel(BaseModel):
    """Acción que se aplica al alcanzar un nivel de strikes (HU-41)."""

    model_config = ConfigDict(extra="forbid")

    nivel: int = Field(ge=1, description="Nivel de strikes al que aplica la acción", examples=[3])
    accion: Literal["ADVERTENCIA", "BLOQUEO"] = Field(
        description="ADVERTENCIA (solo avisa) o BLOQUEO (impide nuevas solicitudes)"
    )


class ParametroSancionOut(BaseModel):
    tolerancia_minutos: int = Field(description="Minutos de tolerancia desde el inicio de la reserva")
    aviso_minutos: int = Field(description="Minutos después del inicio en que se envía la advertencia")
    minutos_por_strike: int = Field(description="Minutos de retraso que equivalen a un strike")
    max_strikes: int = Field(description="Strikes activos que bloquean las nuevas solicitudes")
    acciones: list[AccionNivel] = Field(description="Acción configurada para cada nivel de strikes")
    actualizado_en: datetime | None = Field(description="Última modificación de la política")


class ParametroSancionActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tolerancia_minutos: int = Field(gt=0, le=240, description="Tolerancia en minutos", examples=[10])
    aviso_minutos: int = Field(ge=0, le=239, description="Minutos para la advertencia", examples=[5])
    minutos_por_strike: int = Field(gt=0, le=240, description="Minutos por strike", examples=[10])
    max_strikes: int = Field(gt=0, le=20, description="Máximo de strikes", examples=[3])
    acciones: list[AccionNivel] = Field(
        min_length=1,
        max_length=20,
        description="Acción por nivel de strikes (niveles sin fila solo avisan)",
    )

    @model_validator(mode="after")
    def aviso_antes_de_tolerancia(self):
        if self.aviso_minutos >= self.tolerancia_minutos:
            raise ValueError("Los minutos de aviso deben ser menores que la tolerancia")
        return self


class StrikeOut(BaseModel):
    id: int
    reserva_id: int
    espacio: str
    inicio: datetime | None = Field(description="Inicio de la reserva que originó el strike")
    minutos_retraso: int
    anulado: bool
    motivo_anulacion: str | None
    creada_en: datetime


class ReactivacionOut(BaseModel):
    id: int
    usuario_id: int
    usuario: str
    estado: EstadoReactivacion
    justificacion: str
    detalle: list[dict] = Field(description="Justificación registrada para cada strike")
    strikes_anulados: int
    creada_en: datetime
    decidida_por: str | None
    fecha_decision: datetime | None
    motivo_rechazo: str | None


class JustificacionStrike(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strike_id: int = Field(gt=0, description="Strike que se justifica")
    justificacion: str = Field(min_length=5, max_length=500, description="Explicación del retraso")


class ReactivacionCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    justificacion: str = Field(
        min_length=10,
        max_length=1000,
        description="Explicación general de por qué pide la reactivación",
    )
    strikes: list[JustificacionStrike] = Field(
        min_length=1,
        description="Justificación de cada strike activo",
    )

    @model_validator(mode="after")
    def sin_duplicados(self):
        ids = [item.strike_id for item in self.strikes]
        if len(ids) != len(set(ids)):
            raise ValueError("No se puede justificar dos veces el mismo strike")
        return self


class ReactivacionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aprobar: bool = Field(description="true para reactivar, false para rechazar")
    strikes_anular: list[int] = Field(
        default_factory=list,
        description="Strikes que se anulan al aceptar la reactivación",
    )
    motivo: str | None = Field(
        default=None,
        max_length=500,
        description="Motivo del rechazo; obligatorio cuando aprobar es false",
    )

    @model_validator(mode="after")
    def decision_coherente(self):
        if self.aprobar and not self.strikes_anular:
            raise ValueError("Indica al menos un strike para anular")
        if not self.aprobar and not (self.motivo or "").strip():
            raise ValueError("Indica el motivo del rechazo")
        return self


class MiEstadoSancionOut(BaseModel):
    bloqueado: bool = Field(description="true si no puede crear nuevas solicitudes")
    strikes_activos: int
    max_strikes: int
    tolerancia_minutos: int
    aviso_minutos: int
    strikes: list[StrikeOut]
    reactivacion: ReactivacionOut | None = Field(
        description="Reactivación pendiente o la última resuelta"
    )


class UsuarioSancionadoOut(BaseModel):
    usuario_id: int
    nombre: str
    email: str
    rol: str
    cargo: str | None
    strikes_activos: int
    bloqueado: bool
    strikes: list[StrikeOut]
    reactivacion: ReactivacionOut | None


class ReporteSancionesOut(BaseModel):
    total_usuarios: int
    total_bloqueados: int
    usuarios: list[UsuarioSancionadoOut]
    reactivaciones_pendientes: list[ReactivacionOut]


class AsistenciaOut(BaseModel):
    reserva_id: int
    estado: str = Field(description="Estado de la reserva")
    estado_asistencia: str = Field(description="PENDIENTE, ASISTIO o NO_ASISTIO")
    inicio_efectivo: datetime | None = Field(description="Hora real en que se registró la asistencia")
    mensaje: str
