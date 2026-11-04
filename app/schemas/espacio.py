from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import TipoEspacio


class EspacioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Identificador del espacio", examples=[1])
    nombre: str = Field(description="Nombre del laboratorio o sala", examples=["Laboratorio de Redes"])
    tipo: TipoEspacio = Field(description="LABORATORIO o SALA")
    capacidad: int = Field(description="Número máximo de personas", examples=[25])
    ubicacion: str | None = Field(description="Bloque y piso", examples=["Bloque A, piso 2"])


class EspacioMetricaOut(BaseModel):
    id: int = Field(description="Identificador del espacio")
    nombre: str = Field(description="Nombre del espacio")
    tipo: TipoEspacio = Field(description="LABORATORIO o SALA")
    capacidad: int = Field(description="Número máximo de personas")
    ubicacion: str | None = Field(description="Bloque y piso")
    activo: bool = Field(description="false si el espacio no está habilitado")
    fecha: date = Field(description="Fecha consultada")
    reservas_dia: int = Field(description="Reservas ACTIVAS que se cruzan con la fecha")
    minutos_reservados: float = Field(description="Minutos reservados dentro del horario operativo")
    minutos_disponibles: int = Field(description="Minutos del horario operativo; 0 si está cerrado o inactivo")
    porcentaje_ocupacion: float | None = Field(
        description="Minutos reservados sobre minutos disponibles; null si no hay horario reservable"
    )


class EspacioCrear(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "nombre": "Laboratorio de Redes",
                "tipo": "LABORATORIO",
                "capacidad": 25,
                "ubicacion": "Bloque A, piso 2",
                "amenidades": [1, 3],
            }
        },
    )

    nombre: str = Field(max_length=120, description="Nombre del espacio, único")
    tipo: TipoEspacio = Field(description="LABORATORIO o SALA")
    capacidad: int = Field(gt=0, description="Número máximo de personas")
    ubicacion: str | None = Field(None, max_length=200, description="Bloque y piso (opcional)")
    amenidades: list[int] = Field(
        default_factory=list,
        description=(
            "Ids de recursos del catálogo que quedan instalados en el espacio. Cada uno "
            "descuenta una unidad del stock disponible"
        ),
    )

    @field_validator("amenidades")
    @classmethod
    def _sin_repetidos(cls, valor: list[int]) -> list[int]:
        if len(valor) != len(set(valor)):
            raise ValueError("No se puede repetir la misma amenidad en un espacio")
        return valor

    @field_validator("nombre")
    @classmethod
    def _nombre_no_vacio(cls, valor: str) -> str:
        nombre = valor.strip()
        if not nombre:
            raise ValueError("El nombre no puede estar vacío")
        return nombre

    @field_validator("ubicacion")
    @classmethod
    def _normalizar_ubicacion(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return valor.strip() or None


class EspacioActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(None, max_length=120, description="Nombre del espacio")
    tipo: TipoEspacio | None = Field(None, description="LABORATORIO o SALA")
    capacidad: int | None = Field(None, gt=0, description="Número máximo de personas")
    ubicacion: str | None = Field(None, max_length=200, description="Bloque y piso; null para quitarla")
    amenidades: list[int] | None = Field(
        None,
        description=(
            "Ids de recursos que quedan instalados. Si se omite no se tocan; una lista vacía "
            "libera todas las amenidades del espacio"
        ),
    )

    @field_validator("amenidades")
    @classmethod
    def _sin_repetidos(cls, valor: list[int] | None) -> list[int] | None:
        if valor is not None and len(valor) != len(set(valor)):
            raise ValueError("No se puede repetir la misma amenidad en un espacio")
        return valor

    @field_validator("nombre", "tipo", "capacidad", mode="before")
    @classmethod
    def _campos_requeridos_no_nulos(cls, valor):
        if valor is None:
            raise ValueError("Este campo no puede ser null")
        return valor

    @field_validator("nombre")
    @classmethod
    def _nombre_no_vacio(cls, valor: str) -> str:
        nombre = valor.strip()
        if not nombre:
            raise ValueError("El nombre no puede estar vacío")
        return nombre

    @field_validator("ubicacion")
    @classmethod
    def _normalizar_ubicacion(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return valor.strip() or None

    @model_validator(mode="after")
    def _requiere_cambios(self):
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar")
        return self


class EspacioEstadoActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"activo": False}})

    activo: bool = Field(description="false desactiva el espacio; true lo reactiva")


class AmenidadEspacioOut(BaseModel):
    tipo_recurso_id: int = Field(description="Identificador del recurso")
    nombre: str = Field(description="Nombre del recurso")


class EspacioAdminOut(EspacioOut):
    activo: bool = Field(description="false si el espacio está desactivado")
    amenidades: list[AmenidadEspacioOut] = Field(
        default_factory=list, description="Recursos instalados de forma fija en el espacio"
    )
