from datetime import datetime, time

from sqlalchemy import (
    JSON,
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
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import (
    AccionTrazabilidad,
    Cargo,
    EstadoAsignacion,
    EstadoAsistencia,
    EstadoReactivacion,
    EstadoRecurso,
    EstadoReserva,
    EstadoSolicitud,
    EstadoSolicitudRecurso,
    Rol,
    RolReserva,
    TipoEspacio,
    TipoNotificacion,
)

# Días de la semana ISO (1 = lunes ... 7 = domingo) que un espacio opera por defecto
DIAS_OPERACION_DEFECTO = "1,2,3,4,5,6,7"


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
    # HU-35: permiso para decidir solicitudes fuera de la franja de operación
    puede_autorizar_especial: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Qué aprobadores gestionan cada espacio (HU-08)
espacio_aprobador = Table(
    "espacio_aprobador",
    Base.metadata,
    Column("espacio_id", ForeignKey("espacio.id", ondelete="CASCADE"), primary_key=True),
    Column("usuario_id", ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True),
)


class TipoUso(Base):
    """Catálogo de actividades permitidas (HU-22): clases, exámenes, auditorías..."""

    __tablename__ = "tipo_uso"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Qué actividades permite cada espacio (HU-22, HU-29)
espacio_tipo_uso = Table(
    "espacio_tipo_uso",
    Base.metadata,
    Column("espacio_id", ForeignKey("espacio.id", ondelete="CASCADE"), primary_key=True),
    Column("tipo_uso_id", ForeignKey("tipo_uso.id", ondelete="CASCADE"), primary_key=True),
)


class ReglaAnticipacionRol(Base):
    """Anticipación máxima, en días, con la que reserva cada rol (HU-32, HU-37).

    Si el rol no tiene fila, no tiene límite de anticipación.
    """

    __tablename__ = "regla_anticipacion_rol"
    __table_args__ = (CheckConstraint("dias_maximos > 0", name="dias_positivos"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rol: Mapped[RolReserva] = mapped_column(_enum(RolReserva, "rol_reserva"), unique=True)
    dias_maximos: Mapped[int] = mapped_column(Integer)
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Espacio(Base):
    __tablename__ = "espacio"
    __table_args__ = (
        CheckConstraint("capacidad > 0", name="capacidad_positiva"),
        # Franja de operación (HU-21, HU-34): las dos horas o ninguna
        CheckConstraint(
            "(hora_apertura IS NULL AND hora_cierre IS NULL) "
            "OR (hora_apertura IS NOT NULL AND hora_cierre IS NOT NULL)",
            name="franja_completa",
        ),
        CheckConstraint(
            "hora_cierre IS NULL OR hora_cierre > hora_apertura", name="franja_ordenada"
        ),
        CheckConstraint("max_usos_dia IS NULL OR max_usos_dia > 0", name="max_usos_positivo"),
        CheckConstraint(
            "duracion_maxima_min IS NULL OR duracion_maxima_min > 0", name="duracion_positiva"
        ),
        CheckConstraint("separacion_min >= 0", name="separacion_no_negativa"),
        CheckConstraint(
            "ocupacion_minima IS NULL OR ocupacion_minima > 0", name="ocupacion_positiva"
        ),
        CheckConstraint(
            "ocupacion_minima IS NULL OR ocupacion_minima <= capacidad", name="ocupacion_cabe"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    tipo: Mapped[TipoEspacio] = mapped_column(_enum(TipoEspacio, "tipo_espacio"))
    capacidad: Mapped[int] = mapped_column(Integer)
    ubicacion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    # HU-21 / HU-34: franja de operación propia del espacio. Si es NULL se usa la
    # franja institucional de app.utils.fechas.
    hora_apertura: Mapped[time | None] = mapped_column(Time, nullable=True)
    hora_cierre: Mapped[time | None] = mapped_column(Time, nullable=True)
    dias_operacion: Mapped[str] = mapped_column(
        String(20), server_default=text(f"'{DIAS_OPERACION_DEFECTO}'")
    )

    # HU-28 / HU-33 / HU-34 / HU-36
    max_usos_dia: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duracion_maxima_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    separacion_min: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    ocupacion_minima: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requiere_responsable: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    admite_autorizacion_especial: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )

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
        # HU-35: la autorización especial se registra completa o no se registra
        CheckConstraint(
            "(autorizado_por IS NULL AND fecha_autorizacion IS NULL) "
            "OR (autorizado_por IS NOT NULL AND fecha_autorizacion IS NOT NULL)",
            name="autorizacion_con_responsable",
        ),
        Index("ix_solicitud_espacio_estado", "espacio_id", "estado"),
        Index("ix_solicitud_solicitante", "solicitante_id"),
        CheckConstraint("prioridad BETWEEN 0 AND 3", name="prioridad_valida"),
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
    # HU-29: actividad declarada, del catálogo de tipos de uso
    tipo_uso_id: Mapped[int | None] = mapped_column(ForeignKey("tipo_uso.id"), nullable=True)
    # HU-32: docente/coordinador/director responsable de la actividad
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    # HU-30 (bloque 2): motivo obligatorio al pedir el cupo de alguien de menor jerarquía
    motivo_urgencia: Mapped[str | None] = mapped_column(Text, nullable=True)
    # HU-30 / HU-31: dueño del cupo que se pone en juego cuando hay conflicto de jerarquía
    titular_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    # HU-35: quién autorizó el uso fuera de la franja y cuándo
    autorizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    fecha_autorizacion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # HU-12: nivel de prioridad según el rol de reserva de quien solicita (0 a 3)
    prioridad: Mapped[int] = mapped_column(Integer, server_default=text("0"))
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
        Index("ix_reserva_asistencia", "estado", "estado_asistencia", "inicio"),
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
    # HU-17: motivo que registra el solicitante al cancelar
    motivo_cancelacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # HU-38 / HU-39: asistencia efectiva y aviso previo al no-show
    estado_asistencia: Mapped[EstadoAsistencia] = mapped_column(
        _enum(EstadoAsistencia, "estado_asistencia"), server_default=text("'PENDIENTE'")
    )
    inicio_efectivo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    advertencia_enviada: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Las reservas anteriores a la funcionalidad no generan no-show ni strikes
    sancionable: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
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


class RegistroConfiguracion(Base):
    """Auditoría de cambios de configuración (HU-36, HU-37, HU-41).

    La tabla de trazabilidad está atada a una solicitud, y estos cambios no lo
    están: por eso se guardan aparte, con usuario, fecha y hora.
    """

    __tablename__ = "registro_configuracion"
    __table_args__ = (Index("ix_registro_configuracion_fecha", "fecha", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    # NULL cuando el cambio no es de un espacio (por ejemplo, la anticipación por rol)
    espacio_id: Mapped[int | None] = mapped_column(ForeignKey("espacio.id"), nullable=True)
    entidad: Mapped[str] = mapped_column(String(30))
    detalle: Mapped[str] = mapped_column(Text)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


class Notificacion(Base):
    """Aviso interno para un usuario (HU-31, y reutilizable por otras historias).

    Se crea en la misma transacción de la acción que la origina: si la acción
    falla, la notificación tampoco queda.
    """

    __tablename__ = "notificacion"
    __table_args__ = (
        Index("ix_notificacion_usuario_lectura", "usuario_id", "leida", "creada_en"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    tipo: Mapped[TipoNotificacion] = mapped_column(_enum(TipoNotificacion, "tipo_notificacion"))
    titulo: Mapped[str] = mapped_column(String(160))
    mensaje: Mapped[str] = mapped_column(Text)
    # Solicitud que originó el aviso (la cesión, por ejemplo)
    solicitud_id: Mapped[int | None] = mapped_column(ForeignKey("solicitud.id"), nullable=True)
    leida: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


class ParametroSancion(Base):
    """Política de tolerancia, strikes y sanciones (HU-39, HU-40, HU-41).

    Es una fila única (id=1). Las reservas creadas antes de activar la
    funcionalidad quedan con `sancionable = false` y no generan no-show.
    """

    __tablename__ = "parametro_sancion"
    __table_args__ = (
        CheckConstraint("tolerancia_minutos > 0", name="tolerancia_positiva"),
        CheckConstraint("aviso_minutos >= 0", name="aviso_no_negativo"),
        CheckConstraint("aviso_minutos < tolerancia_minutos", name="aviso_menor_que_tolerancia"),
        CheckConstraint("minutos_por_strike > 0", name="minutos_strike_positivos"),
        CheckConstraint("max_strikes > 0", name="max_strikes_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    tolerancia_minutos: Mapped[int] = mapped_column(Integer, server_default=text("10"))
    aviso_minutos: Mapped[int] = mapped_column(Integer, server_default=text("5"))
    minutos_por_strike: Mapped[int] = mapped_column(Integer, server_default=text("10"))
    max_strikes: Mapped[int] = mapped_column(Integer, server_default=text("3"))
    # Nivel de strikes -> acción (ADVERTENCIA o BLOQUEO), editable por el ADMIN
    acciones: Mapped[list] = mapped_column(
        JSON,
        server_default=text(
            """'[{"nivel": 1, "accion": "ADVERTENCIA"}, """
            """{"nivel": 2, "accion": "ADVERTENCIA"}, """
            """{"nivel": 3, "accion": "BLOQUEO"}]'"""
        ),
    )
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Reactivacion(Base):
    """Solicitud de reactivación de un usuario bloqueado (HU-42)."""

    __tablename__ = "reactivacion"
    __table_args__ = (Index("ix_reactivacion_usuario_estado", "usuario_id", "estado"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    estado: Mapped[EstadoReactivacion] = mapped_column(
        _enum(EstadoReactivacion, "estado_reactivacion"), server_default=text("'PENDIENTE'")
    )
    justificacion: Mapped[str] = mapped_column(Text)
    # Justificación por strike: [{"strike_id": 1, "justificacion": "..."}]
    detalle: Mapped[list] = mapped_column(JSON, server_default=text("'[]'"))
    strikes_anulados: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    decidida_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    fecha_decision: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo_rechazo: Mapped[str | None] = mapped_column(Text, nullable=True)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


class Strike(Base):
    """Strike acumulado por un no-show (HU-40)."""

    __tablename__ = "strike"
    __table_args__ = (
        CheckConstraint("minutos_retraso >= 0", name="minutos_no_negativos"),
        Index("ix_strike_usuario_anulado", "usuario_id", "anulado"),
        Index("ix_strike_reserva", "reserva_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    reserva_id: Mapped[int] = mapped_column(ForeignKey("reserva.id"))
    minutos_retraso: Mapped[int] = mapped_column(Integer)
    anulado: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    anulado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    motivo_anulacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    reactivacion_id: Mapped[int | None] = mapped_column(
        ForeignKey("reactivacion.id"), nullable=True
    )
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


# --------------------------------------------------------------------------- #
# Recursos tecnológicos (HU-43 a HU-46)
# --------------------------------------------------------------------------- #
class TipoRecurso(Base):
    """Categoría del inventario tecnológico (HU-43): video beam, cámara, etc."""

    __tablename__ = "tipo_recurso"
    __table_args__ = (
        Index("ux_tipo_recurso_nombre_lower", text("lower(nombre)"), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


class Recurso(Base):
    """Unidad física del inventario, con la etiqueta del objeto (HU-43)."""

    __tablename__ = "recurso"
    __table_args__ = (
        Index("ux_recurso_codigo_lower", text("lower(codigo)"), unique=True),
        Index("ix_recurso_tipo_estado", "tipo_recurso_id", "estado", "activo"),
        # Una amenidad por espacio: una unidad instalada no se repite en el mismo espacio
        Index(
            "ux_recurso_amenidad",
            "espacio_id",
            "tipo_recurso_id",
            unique=True,
            postgresql_where=text("espacio_id IS NOT NULL AND activo"),
        ),
        CheckConstraint(
            "estado IN ('EN_FUNCIONAMIENTO', 'FALLIDO')", name="estado_recurso_valido"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo_recurso_id: Mapped[int] = mapped_column(ForeignKey("tipo_recurso.id"))
    # Identificador único que corresponde a la etiqueta física (HU-43, criterio 3)
    codigo: Mapped[str] = mapped_column(String(40))
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[EstadoRecurso] = mapped_column(
        _enum(EstadoRecurso, "estado_recurso"), server_default=text("'EN_FUNCIONAMIENTO'")
    )
    # Comentario del administrador al recibir o revisar la unidad (criterio 4)
    comentario_estado: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Amenidad: unidad instalada de forma fija en un espacio (HU-43, criterio 7 / HU-19).
    # Si tiene espacio no se presta y descuenta del stock disponible.
    espacio_id: Mapped[int | None] = mapped_column(ForeignKey("espacio.id"), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


class SolicitudRecurso(Base):
    """Solicitud de recursos ligada a una reserva de espacio (HU-44)."""

    __tablename__ = "solicitud_recurso"
    __table_args__ = (
        Index("ix_solicitud_recurso_estado_creada", "estado", "creada_en"),
        Index("ix_solicitud_recurso_reserva", "reserva_id"),
        Index("ix_solicitud_recurso_solicitante", "solicitante_id", "creada_en"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reserva_id: Mapped[int] = mapped_column(ForeignKey("reserva.id"))
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    estado: Mapped[EstadoSolicitudRecurso] = mapped_column(
        _enum(EstadoSolicitudRecurso, "estado_solicitud_recurso"),
        server_default=text("'PENDIENTE'"),
    )
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    motivo_rechazo: Mapped[str | None] = mapped_column(Text, nullable=True)
    decidido_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    fecha_decision: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


class DetalleSolicitudRecurso(Base):
    """Tipo y cantidad pedidos en una solicitud de recursos (HU-44, criterio 4)."""

    __tablename__ = "detalle_solicitud_recurso"
    __table_args__ = (
        UniqueConstraint(
            "solicitud_recurso_id", "tipo_recurso_id", name="ux_detalle_recurso_tipo"
        ),
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_recurso_id: Mapped[int] = mapped_column(ForeignKey("solicitud_recurso.id"))
    tipo_recurso_id: Mapped[int] = mapped_column(ForeignKey("tipo_recurso.id"))
    cantidad: Mapped[int] = mapped_column(Integer)


class AsignacionRecurso(Base):
    """Unidad concreta asignada, entregada y devuelta (HU-45 y HU-46)."""

    __tablename__ = "asignacion_recurso"
    __table_args__ = (
        CheckConstraint("fin > inicio", name="rango_valido"),
        CheckConstraint("strikes_generados >= 0", name="strikes_no_negativos"),
        # Una unidad no puede tener dos asignaciones vivas en horarios cruzados
        ExcludeConstraint(
            ("recurso_id", "="),
            (text("tstzrange(inicio, fin, '[)')"), "&&"),
            name="ex_asignacion_sin_cruce",
            using="gist",
            where=text("estado IN ('ASIGNADA', 'ENTREGADA')"),
        ),
        Index("ix_asignacion_recurso_estado", "recurso_id", "estado"),
        Index("ix_asignacion_solicitud", "solicitud_recurso_id"),
        Index("ix_asignacion_vencimiento", "estado", "fin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_recurso_id: Mapped[int] = mapped_column(ForeignKey("solicitud_recurso.id"))
    recurso_id: Mapped[int] = mapped_column(ForeignKey("recurso.id"))
    estado: Mapped[EstadoAsignacion] = mapped_column(
        _enum(EstadoAsignacion, "estado_asignacion"), server_default=text("'ASIGNADA'")
    )
    # Ventana de uso: copia del horario de la reserva (HU-44, criterio 6)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entregada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    entregada_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    devuelta_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    devuelta_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    # Estado en que el administrador recibe la unidad (HU-46, criterio 4)
    estado_devolucion: Mapped[EstadoRecurso | None] = mapped_column(
        _enum(EstadoRecurso, "estado_recurso_devolucion"), nullable=True
    )
    comentario_devolucion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Strikes ya generados por retraso: evita duplicarlos entre barridos
    strikes_generados: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    penalizada: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
