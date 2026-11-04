"""Reglas de reserva por espacio, tipos de uso y anticipación por rol.

Bloque 1 de las épicas 6 y 9:

- HU-21 / HU-34: franja de operación y días operables por espacio.
- HU-22 / HU-29: catálogo de tipos de uso y su relación con cada espacio.
- HU-28 / HU-33 / HU-36: ocupación mínima, duración máxima, separación entre
  reservas, máximo de usos por día, responsable exigido y autorización especial.
- HU-32 / HU-37: anticipación máxima por rol de reserva.
- HU-35: estado PENDIENTE_AUTORIZACION y registro de quién autorizó.
- Auditoría de los cambios de configuración (HU-36.8, HU-37.6).

Revision ID: 0002_reglas_reserva
Revises: 0001_baseline
Create Date: 2026-10-29

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_reglas_reserva"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESTADOS_ANTIGUOS = ("PENDIENTE", "APROBADA", "RECHAZADA", "CANCELADA")
ESTADOS_NUEVOS = ESTADOS_ANTIGUOS + ("PENDIENTE_AUTORIZACION", "EN_ESPERA_CESION")

ACCIONES_ANTIGUAS = ("CREADA", "APROBADA", "RECHAZADA", "CANCELADA")
ACCIONES_NUEVAS = ACCIONES_ANTIGUAS + ("AUTORIZADA", "AUTORIZACION_DENEGADA")


def _check_enum(tabla: str, columna: str, constraint: str, valores: tuple[str, ...]) -> str:
    lista = ", ".join(f"'{valor}'" for valor in valores)
    return f"ALTER TABLE {tabla} ADD CONSTRAINT {constraint} CHECK ({columna} IN ({lista}))"


def upgrade() -> None:
    # --- Catálogo de tipos de uso (HU-22) ---
    op.create_table(
        "tipo_uso",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=80), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tipo_uso")),
        sa.UniqueConstraint("nombre", name=op.f("uq_tipo_uso_nombre")),
    )
    op.create_table(
        "espacio_tipo_uso",
        sa.Column("espacio_id", sa.Integer(), nullable=False),
        sa.Column("tipo_uso_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["espacio_id"],
            ["espacio.id"],
            name=op.f("fk_espacio_tipo_uso_espacio_id_espacio"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tipo_uso_id"],
            ["tipo_uso.id"],
            name=op.f("fk_espacio_tipo_uso_tipo_uso_id_tipo_uso"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("espacio_id", "tipo_uso_id", name=op.f("pk_espacio_tipo_uso")),
    )

    # --- Anticipación máxima por rol (HU-32, HU-37) ---
    op.create_table(
        "regla_anticipacion_rol",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "rol",
            sa.Enum(
                "ESTUDIANTE",
                "DOCENTE",
                "COORDINADOR",
                "DIRECTOR",
                name="rol_reserva",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("dias_maximos", sa.Integer(), nullable=False),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "dias_maximos > 0", name=op.f("ck_regla_anticipacion_rol_dias_positivos")
        ),
        sa.ForeignKeyConstraint(
            ["actualizado_por"],
            ["usuario.id"],
            name=op.f("fk_regla_anticipacion_rol_actualizado_por_usuario"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_regla_anticipacion_rol")),
        sa.UniqueConstraint("rol", name=op.f("uq_regla_anticipacion_rol_rol")),
    )

    # --- Auditoría de configuración (HU-36.8, HU-37.6) ---
    op.create_table(
        "registro_configuracion",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("espacio_id", sa.Integer(), nullable=True),
        sa.Column("entidad", sa.String(length=30), nullable=False),
        sa.Column("detalle", sa.Text(), nullable=False),
        sa.Column(
            "fecha",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["espacio_id"],
            ["espacio.id"],
            name=op.f("fk_registro_configuracion_espacio_id_espacio"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_registro_configuracion_usuario_id_usuario"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registro_configuracion")),
    )
    op.create_index(
        "ix_registro_configuracion_fecha", "registro_configuracion", ["fecha", "id"], unique=False
    )

    # --- Reglas de uso en el espacio (HU-21, HU-28, HU-33, HU-34, HU-36) ---
    op.add_column("espacio", sa.Column("hora_apertura", sa.Time(), nullable=True))
    op.add_column("espacio", sa.Column("hora_cierre", sa.Time(), nullable=True))
    op.add_column(
        "espacio",
        sa.Column(
            "dias_operacion",
            sa.String(length=20),
            server_default=sa.text("'1,2,3,4,5,6,7'"),
            nullable=False,
        ),
    )
    op.add_column("espacio", sa.Column("max_usos_dia", sa.Integer(), nullable=True))
    op.add_column("espacio", sa.Column("duracion_maxima_min", sa.Integer(), nullable=True))
    op.add_column(
        "espacio", sa.Column("separacion_min", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )
    op.add_column("espacio", sa.Column("ocupacion_minima", sa.Integer(), nullable=True))
    op.add_column(
        "espacio",
        sa.Column(
            "requiere_responsable", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column(
        "espacio",
        sa.Column(
            "admite_autorizacion_especial",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    op.create_check_constraint(
        op.f("ck_espacio_franja_completa"),
        "espacio",
        "(hora_apertura IS NULL AND hora_cierre IS NULL) "
        "OR (hora_apertura IS NOT NULL AND hora_cierre IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_espacio_franja_ordenada"),
        "espacio",
        "hora_cierre IS NULL OR hora_cierre > hora_apertura",
    )
    op.create_check_constraint(
        op.f("ck_espacio_max_usos_positivo"), "espacio", "max_usos_dia IS NULL OR max_usos_dia > 0"
    )
    op.create_check_constraint(
        op.f("ck_espacio_duracion_positiva"),
        "espacio",
        "duracion_maxima_min IS NULL OR duracion_maxima_min > 0",
    )
    op.create_check_constraint(
        op.f("ck_espacio_separacion_no_negativa"), "espacio", "separacion_min >= 0"
    )
    op.create_check_constraint(
        op.f("ck_espacio_ocupacion_positiva"),
        "espacio",
        "ocupacion_minima IS NULL OR ocupacion_minima > 0",
    )
    op.create_check_constraint(
        op.f("ck_espacio_ocupacion_cabe"),
        "espacio",
        "ocupacion_minima IS NULL OR ocupacion_minima <= capacidad",
    )

    # --- Datos de la solicitud que exigen las reglas ---
    op.add_column("solicitud", sa.Column("tipo_uso_id", sa.Integer(), nullable=True))
    op.add_column("solicitud", sa.Column("responsable_id", sa.Integer(), nullable=True))
    op.add_column("solicitud", sa.Column("motivo_urgencia", sa.Text(), nullable=True))
    op.add_column("solicitud", sa.Column("autorizado_por", sa.Integer(), nullable=True))
    op.add_column(
        "solicitud", sa.Column("fecha_autorizacion", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_solicitud_responsable_id_usuario"), "solicitud", "usuario", ["responsable_id"], ["id"]
    )
    op.create_foreign_key(
        op.f("fk_solicitud_autorizado_por_usuario"), "solicitud", "usuario", ["autorizado_por"], ["id"]
    )
    op.create_foreign_key(
        op.f("fk_solicitud_tipo_uso_id_tipo_uso"), "solicitud", "tipo_uso", ["tipo_uso_id"], ["id"]
    )
    op.create_check_constraint(
        op.f("ck_solicitud_autorizacion_con_responsable"),
        "solicitud",
        "(autorizado_por IS NULL AND fecha_autorizacion IS NULL) "
        "OR (autorizado_por IS NOT NULL AND fecha_autorizacion IS NOT NULL)",
    )

    # --- Permiso de autorización especial (HU-35) ---
    op.add_column(
        "usuario",
        sa.Column(
            "puede_autorizar_especial", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )

    # --- Nuevos estados y acciones: se recrean los CHECK (Alembic no los compara) ---
    op.drop_constraint(op.f("ck_solicitud_estado_solicitud"), "solicitud", type_="check")
    op.execute(_check_enum("solicitud", "estado", "ck_solicitud_estado_solicitud", ESTADOS_NUEVOS))
    op.drop_constraint(op.f("ck_trazabilidad_accion_trazabilidad"), "trazabilidad", type_="check")
    op.execute(
        _check_enum(
            "trazabilidad", "accion", "ck_trazabilidad_accion_trazabilidad", ACCIONES_NUEVAS
        )
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_trazabilidad_accion_trazabilidad"), "trazabilidad", type_="check")
    op.execute(
        _check_enum(
            "trazabilidad", "accion", "ck_trazabilidad_accion_trazabilidad", ACCIONES_ANTIGUAS
        )
    )
    op.drop_constraint(op.f("ck_solicitud_estado_solicitud"), "solicitud", type_="check")
    op.execute(_check_enum("solicitud", "estado", "ck_solicitud_estado_solicitud", ESTADOS_ANTIGUOS))

    op.drop_column("usuario", "puede_autorizar_especial")

    op.drop_constraint(
        op.f("ck_solicitud_autorizacion_con_responsable"), "solicitud", type_="check"
    )
    op.drop_constraint(op.f("fk_solicitud_tipo_uso_id_tipo_uso"), "solicitud", type_="foreignkey")
    op.drop_constraint(op.f("fk_solicitud_autorizado_por_usuario"), "solicitud", type_="foreignkey")
    op.drop_constraint(op.f("fk_solicitud_responsable_id_usuario"), "solicitud", type_="foreignkey")
    op.drop_column("solicitud", "fecha_autorizacion")
    op.drop_column("solicitud", "autorizado_por")
    op.drop_column("solicitud", "motivo_urgencia")
    op.drop_column("solicitud", "responsable_id")
    op.drop_column("solicitud", "tipo_uso_id")

    for nombre in (
        "ck_espacio_ocupacion_cabe",
        "ck_espacio_ocupacion_positiva",
        "ck_espacio_separacion_no_negativa",
        "ck_espacio_duracion_positiva",
        "ck_espacio_max_usos_positivo",
        "ck_espacio_franja_ordenada",
        "ck_espacio_franja_completa",
    ):
        op.drop_constraint(op.f(nombre), "espacio", type_="check")

    op.drop_column("espacio", "admite_autorizacion_especial")
    op.drop_column("espacio", "requiere_responsable")
    op.drop_column("espacio", "ocupacion_minima")
    op.drop_column("espacio", "separacion_min")
    op.drop_column("espacio", "duracion_maxima_min")
    op.drop_column("espacio", "max_usos_dia")
    op.drop_column("espacio", "dias_operacion")
    op.drop_column("espacio", "hora_cierre")
    op.drop_column("espacio", "hora_apertura")

    op.drop_index("ix_registro_configuracion_fecha", table_name="registro_configuracion")
    op.drop_table("registro_configuracion")
    op.drop_table("regla_anticipacion_rol")
    op.drop_table("espacio_tipo_uso")
    op.drop_table("tipo_uso")
