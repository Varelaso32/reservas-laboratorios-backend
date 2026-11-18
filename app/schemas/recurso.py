"""Esquemas de recursos tecnológicos (HU-43 a HU-46)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import EstadoRecurso


class TipoRecursoOut(BaseModel):
    id: int = Field(description="Identificador del tipo de recurso")
    nombre: str = Field(description="Nombre del tipo", examples=["Video beam"])
    descripcion: str | None = Field(description="Descripción del tipo de recurso")
    activo: bool = Field(description="false si ya no se puede solicitar")
    total: int = Field(description="Unidades activas del tipo")
    instalados: int = Field(description="Unidades instaladas como amenidad de un espacio")
    disponibles: int = Field(description="Unidades libres ahora mismo")
    prestados: int = Field(description="Unidades entregadas y aún no devueltas")
    reservados: int = Field(description="Unidades aprobadas que aún no se entregan")
    fallidos: int = Field(description="Unidades en estado Fallido")


class TipoRecursoCrear(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "nombre": "TV",
                "descripcion": "Televisor para salas",
                "cantidad": 4,
            }
        },
    )

    nombre: str = Field(max_length=80, description="Nombre del tipo, único")
    descripcion: str | None = Field(None, max_length=300, description="Descripción opcional")
    cantidad: int = Field(
        0,
        ge=0,
        le=500,
        description="Cuántas unidades hay: se crean con etiqueta automática",
    )

    @field_validator("nombre")
    @classmethod
    def _no_vacio(cls, valor: str) -> str:
        nombre = valor.strip()
        if not nombre:
            raise ValueError("El nombre del tipo de recurso no puede estar vacío")
        return nombre


class TipoRecursoActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(None, max_length=80, description="Nombre nuevo")
    descripcion: str | None = Field(None, max_length=300, description="Descripción nueva")
    activo: bool | None = Field(None, description="false lo saca del catálogo de solicitudes")
    cantidad: int | None = Field(
        None,
        ge=0,
        le=500,
        description=(
            "Cantidad total de unidades. Si sube se crean unidades nuevas; si baja solo se "
            "eliminan unidades libres (no instaladas ni prestadas)"
        ),
    )

    @field_validator("nombre")
    @classmethod
    def _no_vacio(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        nombre = valor.strip()
        if not nombre:
            raise ValueError("El nombre del tipo de recurso no puede estar vacío")
        return nombre

    @model_validator(mode="after")
    def _requiere_cambios(self):
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar")
        return self


class RecursoOut(BaseModel):
    id: int = Field(description="Identificador de la unidad")
    tipo_recurso_id: int = Field(description="Tipo al que pertenece")
    tipo: str = Field(description="Nombre del tipo")
    codigo: str = Field(description="Etiqueta física única de la unidad", examples=["VB-001"])
    descripcion: str | None = Field(description="Descripción de la unidad")
    estado: EstadoRecurso = Field(description="EN_FUNCIONAMIENTO o FALLIDO")
    comentario_estado: str | None = Field(description="Comentario del último cambio de estado")
    espacio_id: int | None = Field(description="Espacio donde está fijo, si aplica")
    espacio: str | None = Field(description="Nombre del espacio fijo, si aplica")
    activo: bool = Field(description="false si la unidad fue dada de baja")
    actualizado_en: datetime | None = Field(description="Último cambio de la unidad")


class RecursoCrear(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "tipo_recurso_id": 1,
                "codigo": "VB-001",
                "descripcion": "Video beam Epson",
                "espacio_id": None,
            }
        },
    )

    tipo_recurso_id: int = Field(gt=0, description="Tipo de recurso existente")
    codigo: str = Field(max_length=40, description="Etiqueta física única")
    descripcion: str | None = Field(None, max_length=300, description="Descripción de la unidad")
    espacio_id: int | None = Field(None, description="Espacio donde queda como equipamiento fijo")

    @field_validator("codigo")
    @classmethod
    def _codigo_no_vacio(cls, valor: str) -> str:
        codigo = valor.strip()
        if not codigo:
            raise ValueError("El identificador de la unidad no puede estar vacío")
        return codigo


class RecursoActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_recurso_id: int | None = Field(None, gt=0, description="Tipo nuevo")
    codigo: str | None = Field(None, max_length=40, description="Etiqueta física nueva")
    descripcion: str | None = Field(None, max_length=300, description="Descripción nueva")
    espacio_id: int | None = Field(None, description="Espacio fijo; null lo desvincula")
    activo: bool | None = Field(None, description="false da de baja la unidad")

    @field_validator("codigo")
    @classmethod
    def _codigo_no_vacio(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        codigo = valor.strip()
        if not codigo:
            raise ValueError("El identificador de la unidad no puede estar vacío")
        return codigo

    @model_validator(mode="after")
    def _requiere_cambios(self):
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar")
        return self


class RecursoEstadoIn(BaseModel):
    """Cambio de estado de una unidad con el comentario de la revisión (HU-43, criterio 4)."""

    model_config = ConfigDict(extra="forbid")

    estado: EstadoRecurso = Field(description="EN_FUNCIONAMIENTO o FALLIDO")
    comentario: str = Field(min_length=3, max_length=300, description="Motivo de la revisión")

    @field_validator("comentario")
    @classmethod
    def _no_vacio(cls, valor: str) -> str:
        comentario = valor.strip()
        if not comentario:
            raise ValueError("El comentario del cambio de estado es obligatorio")
        return comentario


class StockTipoOut(BaseModel):
    tipo_recurso_id: int = Field(description="Identificador del tipo")
    tipo: str = Field(description="Nombre del tipo")
    total: int = Field(description="Unidades activas en funcionamiento")
    instalados: int = Field(description="Unidades instaladas como amenidad de un espacio")
    disponibles: int = Field(description="Unidades libres en el horario consultado")
    prestados: int = Field(description="Unidades entregadas y aún no devueltas")
    reservados: int = Field(description="Unidades aprobadas que aún no se entregan")
    fallidos: int = Field(description="Unidades en estado Fallido")


class AmenidadOut(BaseModel):
    """Recurso del catálogo visto como amenidad de un espacio (HU-43)."""

    tipo_recurso_id: int = Field(description="Identificador del tipo")
    nombre: str = Field(description="Nombre del recurso")
    descripcion: str | None = Field(description="Descripción del recurso")
    total: int = Field(description="Unidades totales del recurso")
    instalados: int = Field(description="Unidades ya instaladas en espacios")
    disponibles: int = Field(description="Unidades que aún se pueden instalar")
    instalado_aqui: bool = Field(
        default=False, description="true si el espacio consultado ya tiene esta amenidad"
    )


class DisponibilidadOut(BaseModel):
    reserva_id: int = Field(description="Reserva consultada")
    espacio: str = Field(description="Nombre del espacio")
    inicio: datetime = Field(description="Inicio del horario de la reserva")
    fin: datetime = Field(description="Fin del horario de la reserva")
    tipos: list[StockTipoOut] = Field(description="Disponibilidad por tipo en ese horario")


class DetalleRecursoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_recurso_id: int = Field(gt=0, description="Tipo solicitado")
    cantidad: int = Field(gt=0, le=50, description="Unidades pedidas")


class SolicitudRecursoCrear(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "reserva_id": 12,
                "detalle": [{"tipo_recurso_id": 1, "cantidad": 2}],
                "observacion": "Para la exposición del proyecto final",
            }
        },
    )

    reserva_id: int = Field(gt=0, description="Reserva propia ACTIVA a la que van los recursos")
    detalle: list[DetalleRecursoIn] = Field(min_length=1, description="Tipos y cantidades")
    observacion: str | None = Field(None, max_length=300, description="Observación opcional")

    @model_validator(mode="after")
    def _sin_tipos_repetidos(self):
        tipos = [linea.tipo_recurso_id for linea in self.detalle]
        if len(tipos) != len(set(tipos)):
            raise ValueError("No se puede repetir el mismo tipo de recurso en la solicitud")
        return self


class DetalleRecursoOut(BaseModel):
    tipo_recurso_id: int = Field(description="Tipo solicitado")
    tipo: str = Field(description="Nombre del tipo")
    cantidad: int = Field(description="Unidades pedidas")
    asignados: int = Field(description="Unidades ya asignadas")


class AsignacionOut(BaseModel):
    id: int = Field(description="Identificador de la asignación")
    recurso_id: int = Field(description="Unidad asignada")
    codigo: str = Field(description="Etiqueta física de la unidad")
    tipo: str = Field(description="Tipo de la unidad")
    estado: str = Field(description="ASIGNADA, ENTREGADA, DEVUELTA o CANCELADA")
    entregada_en: datetime | None = Field(description="Momento de la entrega")
    devuelta_en: datetime | None = Field(description="Momento de la devolución")
    estado_devolucion: EstadoRecurso | None = Field(description="Estado reportado al devolver")
    comentario_devolucion: str | None = Field(description="Comentario de la devolución")
    strikes_generados: int = Field(description="Strikes generados por devolución tardía")


class SolicitudRecursoOut(BaseModel):
    id: int = Field(description="Identificador de la solicitud de recursos")
    reserva_id: int = Field(description="Reserva asociada")
    espacio_id: int = Field(description="Espacio de la reserva")
    espacio: str = Field(description="Nombre del espacio")
    inicio: datetime = Field(description="Inicio de la reserva")
    fin: datetime = Field(description="Fin de la reserva y hora límite de devolución")
    solicitante_id: int = Field(description="Usuario que pidió los recursos")
    solicitante: str = Field(description="Nombre del solicitante")
    estado: str = Field(description="PENDIENTE, APROBADA, RECHAZADA, CANCELADA o DEVUELTA")
    observacion: str | None = Field(description="Observación del solicitante")
    motivo_rechazo: str | None = Field(description="Motivo del rechazo")
    creada_en: datetime = Field(description="Momento en que se registró la solicitud")
    decidida_por: str | None = Field(description="Administrador que decidió")
    fecha_decision: datetime | None = Field(description="Momento de la decisión")
    detalle: list[DetalleRecursoOut] = Field(description="Tipos y cantidades pedidos")
    asignaciones: list[AsignacionOut] = Field(description="Unidades asignadas a la solicitud")


class DecisionSolicitudRecursoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aprobar: bool = Field(description="true aprueba y asigna unidades; false rechaza")
    motivo: str | None = Field(None, max_length=300, description="Obligatorio al rechazar")

    @model_validator(mode="after")
    def _motivo_al_rechazar(self):
        if not self.aprobar and not (self.motivo or "").strip():
            raise ValueError("Debe indicar el motivo del rechazo")
        return self


class DevolucionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: EstadoRecurso = Field(
        description="Estado en que se recibe la unidad: EN_FUNCIONAMIENTO o FALLIDO"
    )
    comentario: str | None = Field(None, max_length=300, description="Comentario de la devolución")


class ReservaElegibleOut(BaseModel):
    reserva_id: int = Field(description="Reserva propia disponible para pedir recursos")
    espacio_id: int = Field(description="Espacio de la reserva")
    espacio: str = Field(description="Nombre del espacio")
    inicio: datetime = Field(description="Inicio de la reserva")
    fin: datetime = Field(description="Fin de la reserva")


class HistorialRecursoOut(BaseModel):
    id: int = Field(description="Identificador de la asignación")
    solicitud_recurso_id: int = Field(description="Solicitud de recursos asociada")
    reserva_id: int = Field(description="Reserva asociada")
    recurso_id: int = Field(description="Unidad prestada")
    codigo: str = Field(description="Etiqueta física de la unidad")
    tipo: str = Field(description="Tipo de la unidad")
    solicitante: str = Field(description="Quién tuvo la unidad")
    inicio: datetime = Field(description="Inicio del uso")
    fin: datetime = Field(description="Hora límite de devolución")
    estado: str = Field(description="Estado de la asignación")
    entregada_en: datetime | None = Field(description="Momento de la entrega")
    devuelta_en: datetime | None = Field(description="Momento de la devolución")
    estado_devolucion: EstadoRecurso | None = Field(description="Estado reportado al devolver")
    comentario_devolucion: str | None = Field(description="Comentario de la devolución")
    strikes_generados: int = Field(description="Strikes generados por devolución tardía")


class ProcesarRetrasosOut(BaseModel):
    notificados: int = Field(description="Devoluciones tardías detectadas en este barrido")
    strikes: int = Field(description="Strikes generados en este barrido")
