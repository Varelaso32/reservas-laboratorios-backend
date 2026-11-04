"""Cupo por orden de llegada, cesión y notificaciones.

Bloque 2 de la épica 9:

- HU-30: `solicitud.titular_id` guarda el dueño del cupo cuando una solicitud
  de mayor jerarquía pide un horario ocupado.
- HU-31: tabla `notificacion` para avisar al titular y permitirle decidir.
- Trazabilidad: acciones CONFLICTO_RECHAZADO, CESION_SOLICITADA,
  CESION_ACEPTADA y CESION_RECHAZADA.

Revision ID: 0003_cesion_notificaciones
Revises: 0002_reglas_reserva
Create Date: 2026-10-29

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_cesion_notificaciones"
down_revision: str | None = "0002_reglas_reserva"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACCIONES_ANTIGUAS = (
    "CREADA",
    "APROBADA",
    "RECHAZADA",
    "CANCELADA",
    "AUTORIZADA",
    "AUTORIZACION_DENEGADA",
)
ACCIONES_NUEVAS = ACCIONES_ANTIGUAS + (
    "CONFLICTO_RECHAZADO",
    "CESION_SOLICITADA",
    "CESION_ACEPTADA",
    "CESION_RECHAZADA",
)

TIPOS_NOTIFICACION = (
    "CESION_SOLICITADA",
    "CESION_ACEPTADA",
    "CESION_RECHAZADA",
    "CESION_CONFIRMADA",
)


def _check_enum(tabla: str, columna: str, constraint: str, valores: tuple[str, ...]) -> str:
    lista = ", ".join(f"'{valor}'" for valor in valores)
    return f"ALTER TABLE {tabla} ADD CONSTRAINT {constraint} CHECK ({columna} IN ({lista}))"


def upgrade() -> None:
    # --- HU-30: dueño del cupo en disputa ---
    op.add_column("solicitud", sa.Column("titular_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_solicitud_titular_id_usuario"),
        "solicitud",
        "usuario",
        ["titular_id"],
        ["id"],
    )

    # --- HU-31: notificaciones internas ---
    op.create_table(
        "notificacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                *TIPOS_NOTIFICACION,
                name="tipo_notificacion",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("solicitud_id", sa.Integer(), nullable=True),
        sa.Column("leida", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["solicitud_id"],
            ["solicitud.id"],
            name=op.f("fk_notificacion_solicitud_id_solicitud"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_notificacion_usuario_id_usuario"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notificacion")),
    )
    op.create_index(
        op.f("ix_notificacion_usuario_lectura"),
        "notificacion",
        ["usuario_id", "leida", "creada_en"],
        unique=False,
    )

    # --- Nuevas acciones de trazabilidad: se recrea el CHECK ---
    op.drop_constraint(op.f("ck_trazabilidad_accion_trazabilidad"), "trazabilidad", type_="check")
    op.execute(
        _check_enum("trazabilidad", "accion", "ck_trazabilidad_accion_trazabilidad", ACCIONES_NUEVAS)
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_trazabilidad_accion_trazabilidad"), "trazabilidad", type_="check")
    op.execute(
        _check_enum("trazabilidad", "accion", "ck_trazabilidad_accion_trazabilidad", ACCIONES_ANTIGUAS)
    )

    op.drop_index(op.f("ix_notificacion_usuario_lectura"), table_name="notificacion")
    op.drop_table("notificacion")

    op.drop_constraint(op.f("fk_solicitud_titular_id_usuario"), "solicitud", type_="foreignkey")
    op.drop_column("solicitud", "titular_id")
