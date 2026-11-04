"""Esquemas de configuración de reglas (HU-21, HU-22, HU-32, HU-35, HU-36, HU-37)."""
from datetime import time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import Cargo, RolReserva, TipoEspacio


class TipoUsoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Identificador del tipo de uso")
    nombre: str = Field(description="Nombre de la actividad", examples=["Clase"])
    activo: bool = Field(description="false si ya no se puede elegir en solicitudes nuevas")


class TipoUsoCrear(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"nombre": "Examen"}})

    nombre: str = Field(max_length=80, description="Nombre de la actividad, único")

    @field_validator("nombre")
    @classmethod
    def _no_vacio(cls, valor: str) -> str:
        nombre = valor.strip()
        if not nombre:
            raise ValueError("El nombre del tipo de uso no puede estar vacío")
        return nombre


class TipoUsoActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(None, max_length=80, description="Nombre nuevo")
    activo: bool | None = Field(None, description="false lo saca del formulario de solicitudes")

    @field_validator("nombre")
    @classmethod
    def _no_vacio(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        nombre = valor.strip()
        if not nombre:
            raise ValueError("El nombre del tipo de uso no puede estar vacío")
        return nombre

    @model_validator(mode="after")
    def _requiere_cambios(self):
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar")
        return self


class ReglasEspacioOut(BaseModel):
    espacio_id: int = Field(description="Identificador del espacio")
    nombre: str = Field(description="Nombre del espacio")
    tipo: TipoEspacio = Field(description="LABORATORIO o SALA")
    capacidad: int = Field(description="Capacidad máxima")
    activo: bool = Field(description="false si el espacio está desactivado")
    hora_apertura: time | None = Field(description="Inicio de la franja; null usa la institucional")
    hora_cierre: time | None = Field(description="Fin de la franja; null usa la institucional")
    dias_operacion: list[int] = Field(description="Días operables, 1 = lunes ... 7 = domingo")
    max_usos_dia: int | None = Field(description="Máximo de usos por día; null sin límite")
    duracion_maxima_min: int | None = Field(description="Duración máxima por uso; null sin límite")
    separacion_min: int = Field(description="Minutos de separación entre reservas")
    ocupacion_minima: int | None = Field(description="Asistentes mínimos; null sin mínimo")
    requiere_responsable: bool = Field(description="true si exige responsable docente o superior")
    admite_autorizacion_especial: bool = Field(
        description="true si acepta solicitudes fuera de la franja para autorización"
    )
    tipos_uso: list[TipoUsoOut] = Field(description="Actividades configuradas para el espacio")


class ReglasEspacioActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hora_apertura: time | None = Field(None, description="Inicio de la franja; null la quita")
    hora_cierre: time | None = Field(None, description="Fin de la franja; null la quita")
    dias_operacion: list[int] | None = Field(
        None, description="Días operables (1 lunes ... 7 domingo). null los deja como están"
    )
    max_usos_dia: int | None = Field(None, description="Máximo de usos por día; null sin límite")
    duracion_maxima_min: int | None = Field(None, description="Duración máxima por uso en minutos")
    separacion_min: int | None = Field(None, ge=0, description="Minutos de separación entre reservas")
    ocupacion_minima: int | None = Field(None, description="Asistentes mínimos; null sin mínimo")
    requiere_responsable: bool | None = Field(None, description="Exigir responsable")
    admite_autorizacion_especial: bool | None = Field(None, description="Admitir autorización especial")
    tipos_uso_ids: list[int] | None = Field(
        None, description="Actividades permitidas; [] deja el espacio sin restricción de actividad"
    )

    @field_validator("dias_operacion")
    @classmethod
    def _dias_validos(cls, valor: list[int] | None) -> list[int] | None:
        if valor is None:
            return None
        if not valor:
            raise ValueError("Debe indicar al menos un día de operación")
        if any(dia < 1 or dia > 7 for dia in valor):
            raise ValueError("Los días van de 1 (lunes) a 7 (domingo)")
        return sorted(set(valor))

    @field_validator("max_usos_dia", "duracion_maxima_min", "ocupacion_minima")
    @classmethod
    def _positivos(cls, valor: int | None) -> int | None:
        if valor is not None and valor <= 0:
            raise ValueError("El valor debe ser un entero positivo")
        return valor

    @model_validator(mode="after")
    def _franja_coherente(self):
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar")
        # Solo se valida cuando el cuerpo trae las dos horas: si trae una sola, la
        # combinación final con la BD puede quedar incompleta.
        if "hora_apertura" in self.model_fields_set and "hora_cierre" in self.model_fields_set:
            if (self.hora_apertura is None) != (self.hora_cierre is None):
                raise ValueError("La franja necesita hora de apertura y de cierre, o ninguna")
            if (
                self.hora_apertura is not None
                and self.hora_cierre is not None
                and self.hora_cierre <= self.hora_apertura
            ):
                raise ValueError("La hora de cierre debe ser posterior a la de apertura")
        return self


class ReglasPorTipoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoEspacio = Field(description="Tipo de espacio al que se aplican las reglas")
    reglas: ReglasEspacioActualizar = Field(description="Reglas que se copian a cada espacio del tipo")


class AnticipacionOut(BaseModel):
    rol: RolReserva = Field(description="Rol de reserva")
    dias_maximos: int | None = Field(description="Días de anticipación; null sin límite")


class AnticipacionActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dias_maximos: int | None = Field(
        None, description="Días de anticipación; null quita el límite para ese rol"
    )

    @field_validator("dias_maximos")
    @classmethod
    def _positivo(cls, valor: int | None) -> int | None:
        if valor is not None and valor <= 0:
            raise ValueError("La anticipación debe ser un entero positivo")
        return valor


class ResponsableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Identificador del usuario")
    nombre: str = Field(description="Nombre completo")
    cargo: Cargo | None = Field(description="Cargo institucional")
    rol_reserva: RolReserva = Field(description="Nivel de reserva: DOCENTE, COORDINADOR o DIRECTOR")


class AutorizacionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"aprobar": True}})

    aprobar: bool = Field(description="true concede la autorización; false la niega")
    motivo: str | None = Field(
        None, max_length=500, description="Obligatorio al negar; opcional al conceder"
    )

    @field_validator("motivo")
    @classmethod
    def _limpio(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return valor.strip() or None


class AutorizacionOut(BaseModel):
    mensaje: str = Field(description="Resultado de la decisión")
    solicitud: dict = Field(description="Solicitud con su estado nuevo")
