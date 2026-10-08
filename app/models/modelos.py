from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import (
    AccionTrazabilidad,
    Cargo,
    EstadoReserva,
    EstadoSolicitud,
    Rol,
    TipoEspacio,
)


def _enum(clase, nombre):
    # Se guarda como texto con CHECK: más fácil de cambiar que un enum nativo
    return Enum(clase, name=nombre, native_enum=False, create_constraint=True, length=30)


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (
        Index("ux_usuario_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    clave_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[Rol] = mapped_column(_enum(Rol, "rol"))
    cargo: Mapped[Cargo | None] = mapped_column(_enum(Cargo, "cargo"), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Qué aprobadores gestionan cada espacio (HU-08)
espacio_aprobador = Table(
    "espacio_aprobador",
    Base.metadata,
    Column("espacio_id", ForeignKey("espacio.id", ondelete="CASCADE"), primary_key=True),
    Column("usuario_id", ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True),
)


class Espacio(Base):
    __tablename__ = "espacio"
    __table_args__ = (CheckConstraint("capacidad > 0", name="capacidad_positiva"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    tipo: Mapped[TipoEspacio] = mapped_column(_enum(TipoEspacio, "tipo_espacio"))
    capacidad: Mapped[int] = mapped_column(Integer)
    ubicacion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Solicitud(Base):
    __tablename__ = "solicitud"
    __table_args__ = (
        CheckConstraint("fin > inicio", name="rango_valido"),
        CheckConstraint("asistentes > 0", name="asistentes_positivos"),
        CheckConstraint(
            "estado <> 'RECHAZADA' OR length(trim(coalesce(motivo_rechazo, ''))) > 0",
            name="rechazo_con_motivo",
        ),
        CheckConstraint(
            "estado NOT IN ('APROBADA', 'RECHAZADA') "
            "OR (decidido_por IS NOT NULL AND fecha_decision IS NOT NULL)",
            name="decision_con_responsable",
        ),
        Index("ix_solicitud_espacio_estado", "espacio_id", "estado"),
        Index("ix_solicitud_solicitante", "solicitante_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    espacio_id: Mapped[int] = mapped_column(ForeignKey("espacio.id"))
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    proposito: Mapped[str] = mapped_column(Text)
    asistentes: Mapped[int] = mapped_column(Integer)
    equipamiento: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[EstadoSolicitud] = mapped_column(
        _enum(EstadoSolicitud, "estado_solicitud"), server_default=text("'PENDIENTE'")
    )
    decidido_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    fecha_decision: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo_rechazo: Mapped[str | None] = mapped_column(Text, nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Reserva(Base):
    __tablename__ = "reserva"
    __table_args__ = (
        CheckConstraint("fin > inicio", name="rango_valido"),
        # La BD impide dos reservas activas cruzadas en el mismo espacio (HU-05, HU-10)
        ExcludeConstraint(
            ("espacio_id", "="),
            (text("tstzrange(inicio, fin, '[)')"), "&&"),
            name="ex_reserva_sin_cruce",
            using="gist",
            where=text("estado = 'ACTIVA'"),
        ),
        Index("ix_reserva_usuario_estado", "usuario_id", "estado"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitud.id"), unique=True)
    espacio_id: Mapped[int] = mapped_column(ForeignKey("espacio.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[EstadoReserva] = mapped_column(
        _enum(EstadoReserva, "estado_reserva"), server_default=text("'ACTIVA'")
    )
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Trazabilidad(Base):
    __tablename__ = "trazabilidad"
    __table_args__ = (Index("ix_trazabilidad_solicitud_orden", "solicitud_id", "fecha", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitud.id"))
    reserva_id: Mapped[int | None] = mapped_column(ForeignKey("reserva.id"), nullable=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    accion: Mapped[AccionTrazabilidad] = mapped_column(_enum(AccionTrazabilidad, "accion_trazabilidad"))
    estado_anterior: Mapped[str | None] = mapped_column(String(30), nullable=True)
    estado_nuevo: Mapped[str | None] = mapped_column(String(30), nullable=True)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    # clock_timestamp() y no now(): now() repite la hora dentro de una misma transacción
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
