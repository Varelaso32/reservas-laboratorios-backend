"""Recursos tecnológicos asociados a una reserva (HU-43 a HU-46).

- HU-43: catálogo de tipos, inventario de unidades con etiqueta física única,
  estado de funcionamiento y auditoría de cambios.
- HU-44: solicitudes de recursos ligadas a una reserva y su detalle por tipo.
- HU-45: asignación de unidades concretas al aprobar, con bloqueo por horario.
- HU-46: entrega, devolución y penalización por retraso.

Revision ID: 0006_recursos
Revises: 0005_asistencia_strikes
Create Date: 2026-10-31

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_recursos"
down_revision: str | None = "0005_asistencia_strikes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACCIONES_TRAZABILIDAD = (
    "CREADA",
    "APROBADA",
    "RECHAZADA",
    "CANCELADA",
    "AUTORIZADA",
    "AUTORIZACION_DENEGADA",
    "CONFLICTO_RECHAZADO",
    "CESION_SOLICITADA",
    "CESION_ACEPTADA",
    "CESION_RECHAZADA",
    "ASISTENCIA_REGISTRADA",
    "ADVERTENCIA_NO_ASISTENCIA",
    "NO_SHOW",
    "STRIKE_ASIGNADO",
    "BLOQUEO_SOLICITUDES",
    "REACTIVACION_SOLICITADA",
    "REACTIVACION_ACEPTADA",
    "REACTIVACION_RECHAZADA",
    "RECURSO_SOLICITADO",
    "RECURSO_APROBADO",
    "RECURSO_RECHAZADO",
    "RECURSO_ASIGNADO",
    "RECURSO_ENTREGADO",
    "RECURSO_DEVUELTO",
    "RECURSO_CANCELADO",
    "RECURSO_PENALIZADO",
)

TIPOS_NOTIFICACION = (
    "CESION_SOLICITADA",
    "CESION_ACEPTADA",
    "CESION_RECHAZADA",
    "CESION_CONFIRMADA",
    "SOLICITUD_RECIBIDA",
    "SOLICITUD_PENDIENTE",
    "SOLICITUD_APROBADA",
    "SOLICITUD_RECHAZADA",
    "SOLICITUD_POR_AUTORIZAR",
    "AUTORIZACION_CONCEDIDA",
    "AUTORIZACION_DENEGADA",
    "ADVERTENCIA_NO_ASISTENCIA",
    "NO_SHOW_REGISTRADO",
    "STRIKE_ASIGNADO",
    "BLOQUEO_SOLICITUDES",
    "REACTIVACION_SOLICITADA",
    "REACTIVACION_ACEPTADA",
    "REACTIVACION_RECHAZADA",
    "RECURSO_SOLICITADO",
    "RECURSO_APROBADO",
    "RECURSO_RECHAZADO",
    "RECURSO_CANCELADO",
    "RECURSO_DEVOLUCION_TARDIA",
)

ESTADOS_RECURSO = ("EN_FUNCIONAMIENTO", "FALLIDO")
ESTADOS_SOLICITUD_RECURSO = ("PENDIENTE", "APROBADA", "RECHAZADA", "CANCELADA", "DEVUELTA")
ESTADOS_ASIGNACION = ("ASIGNADA", "ENTREGADA", "DEVUELTA", "CANCELADA")


def _check(valores: tuple[str, ...]) -> str:
    lista = ", ".join(f"'{valor}'" for valor in valores)
    return f"({lista})"


def upgrade() -> None:
    # --- HU-43: catálogo de tipos --- #
    op.create_table(
        "tipo_recurso",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=80), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tipo_recurso")),
    )
    op.create_index(
        "ux_tipo_recurso_nombre_lower",
        "tipo_recurso",
        [sa.text("lower(nombre)")],
        unique=True,
    )

    # --- HU-43: inventario de unidades --- #
    op.create_table(
        "recurso",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tipo_recurso_id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=40), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column(
            "estado",
            sa.String(length=30),
            server_default=sa.text("'EN_FUNCIONAMIENTO'"),
            nullable=False,
        ),
        sa.Column("comentario_estado", sa.Text(), nullable=True),
        sa.Column("espacio_id", sa.Integer(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tipo_recurso_id"],
            ["tipo_recurso.id"],
            name=op.f("fk_recurso_tipo_recurso_id_tipo_recurso"),
        ),
        sa.ForeignKeyConstraint(
            ["espacio_id"], ["espacio.id"], name=op.f("fk_recurso_espacio_id_espacio")
        ),
        sa.ForeignKeyConstraint(
            ["actualizado_por"],
            ["usuario.id"],
            name=op.f("fk_recurso_actualizado_por_usuario"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recurso")),
        sa.CheckConstraint(
            f"estado IN {_check(ESTADOS_RECURSO)}",
            name=op.f("ck_recurso_estado_recurso_valido"),
        ),
    )
    op.create_index(
        "ux_recurso_codigo_lower", "recurso", [sa.text("lower(codigo)")], unique=True
    )
    op.create_index(
        "ix_recurso_tipo_estado", "recurso", ["tipo_recurso_id", "estado", "activo"]
    )

    # --- HU-44: solicitudes de recursos --- #
    op.create_table(
        "solicitud_recurso",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reserva_id", sa.Integer(), nullable=False),
        sa.Column("solicitante_id", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=30),
            server_default=sa.text("'PENDIENTE'"),
            nullable=False,
        ),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("motivo_rechazo", sa.Text(), nullable=True),
        sa.Column("decidido_por", sa.Integer(), nullable=True),
        sa.Column("fecha_decision", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reserva_id"], ["reserva.id"], name=op.f("fk_solicitud_recurso_reserva_id_reserva")
        ),
        sa.ForeignKeyConstraint(
            ["solicitante_id"],
            ["usuario.id"],
            name=op.f("fk_solicitud_recurso_solicitante_id_usuario"),
        ),
        sa.ForeignKeyConstraint(
            ["decidido_por"],
            ["usuario.id"],
            name=op.f("fk_solicitud_recurso_decidido_por_usuario"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_solicitud_recurso")),
        sa.CheckConstraint(
            f"estado IN {_check(ESTADOS_SOLICITUD_RECURSO)}",
            name=op.f("ck_solicitud_recurso_estado_solicitud_recurso"),
        ),
    )
    op.create_index(
        "ix_solicitud_recurso_estado_creada",
        "solicitud_recurso",
        ["estado", "creada_en"],
    )
    op.create_index("ix_solicitud_recurso_reserva", "solicitud_recurso", ["reserva_id"])
    op.create_index(
        "ix_solicitud_recurso_solicitante",
        "solicitud_recurso",
        ["solicitante_id", "creada_en"],
    )

    op.create_table(
        "detalle_solicitud_recurso",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("solicitud_recurso_id", sa.Integer(), nullable=False),
        sa.Column("tipo_recurso_id", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["solicitud_recurso_id"],
            ["solicitud_recurso.id"],
            name=op.f(
                "fk_detalle_solicitud_recurso_solicitud_recurso_id_solicitud_recurso"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tipo_recurso_id"],
            ["tipo_recurso.id"],
            name=op.f("fk_detalle_solicitud_recurso_tipo_recurso_id_tipo_recurso"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detalle_solicitud_recurso")),
        sa.UniqueConstraint(
            "solicitud_recurso_id",
            "tipo_recurso_id",
            name="ux_detalle_recurso_tipo",
        ),
        sa.CheckConstraint(
            "cantidad > 0", name=op.f("ck_detalle_solicitud_recurso_cantidad_positiva")
        ),
    )

    # --- HU-45 / HU-46: asignaciones, entrega y devolución --- #
    op.create_table(
        "asignacion_recurso",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("solicitud_recurso_id", sa.Integer(), nullable=False),
        sa.Column("recurso_id", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=30),
            server_default=sa.text("'ASIGNADA'"),
            nullable=False,
        ),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entregada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entregada_por", sa.Integer(), nullable=True),
        sa.Column("devuelta_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("devuelta_por", sa.Integer(), nullable=True),
        sa.Column("estado_devolucion", sa.String(length=30), nullable=True),
        sa.Column("comentario_devolucion", sa.Text(), nullable=True),
        sa.Column(
            "strikes_generados", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "penalizada", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["solicitud_recurso_id"],
            ["solicitud_recurso.id"],
            name=op.f(
                "fk_asignacion_recurso_solicitud_recurso_id_solicitud_recurso"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["recurso_id"], ["recurso.id"], name=op.f("fk_asignacion_recurso_recurso_id_recurso")
        ),
        sa.ForeignKeyConstraint(
            ["entregada_por"],
            ["usuario.id"],
            name=op.f("fk_asignacion_recurso_entregada_por_usuario"),
        ),
        sa.ForeignKeyConstraint(
            ["devuelta_por"],
            ["usuario.id"],
            name=op.f("fk_asignacion_recurso_devuelta_por_usuario"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asignacion_recurso")),
        sa.CheckConstraint(
            "fin > inicio", name=op.f("ck_asignacion_recurso_rango_valido")
        ),
        sa.CheckConstraint(
            "strikes_generados >= 0",
            name=op.f("ck_asignacion_recurso_strikes_no_negativos"),
        ),
        sa.CheckConstraint(
            f"estado IN {_check(ESTADOS_ASIGNACION)}",
            name=op.f("ck_asignacion_recurso_estado_asignacion"),
        ),
        sa.CheckConstraint(
            "estado_devolucion IS NULL OR estado_devolucion IN "
            f"{_check(ESTADOS_RECURSO)}",
            name=op.f("ck_asignacion_recurso_estado_recurso_devolucion"),
        ),
        postgresql.ExcludeConstraint(
            ("recurso_id", "="),
            (sa.text("tstzrange(inicio, fin, '[)')"), "&&"),
            name="ex_asignacion_sin_cruce",
            using="gist",
            where=sa.text("estado IN ('ASIGNADA', 'ENTREGADA')"),
        ),
    )
    op.create_index(
        "ix_asignacion_recurso_estado", "asignacion_recurso", ["recurso_id", "estado"]
    )
    op.create_index(
        "ix_asignacion_solicitud", "asignacion_recurso", ["solicitud_recurso_id"]
    )
    op.create_index("ix_asignacion_vencimiento", "asignacion_recurso", ["estado", "fin"])

    # Nuevas acciones del historial (HU-43 a HU-46)
    op.drop_constraint(op.f("ck_trazabilidad_accion_trazabilidad"), "trazabilidad", type_="check")
    op.create_check_constraint(
        op.f("ck_trazabilidad_accion_trazabilidad"),
        "trazabilidad",
        f"accion IN {_check(ACCIONES_TRAZABILIDAD)}",
    )

    # Nuevos tipos de notificación (HU-44 a HU-46)
    op.drop_constraint(op.f("ck_notificacion_tipo_notificacion"), "notificacion", type_="check")
    op.create_check_constraint(
        op.f("ck_notificacion_tipo_notificacion"),
        "notificacion",
        f"tipo IN {_check(TIPOS_NOTIFICACION)}",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_notificacion_tipo_notificacion"), "notificacion", type_="check")
    op.create_check_constraint(
        op.f("ck_notificacion_tipo_notificacion"),
        "notificacion",
        f"tipo IN {_check(TIPOS_NOTIFICACION[:18])}",
    )
    op.drop_constraint(op.f("ck_trazabilidad_accion_trazabilidad"), "trazabilidad", type_="check")
    op.create_check_constraint(
        op.f("ck_trazabilidad_accion_trazabilidad"),
        "trazabilidad",
        f"accion IN {_check(ACCIONES_TRAZABILIDAD[:18])}",
    )

    op.drop_index("ix_asignacion_vencimiento", table_name="asignacion_recurso")
    op.drop_index("ix_asignacion_solicitud", table_name="asignacion_recurso")
    op.drop_index("ix_asignacion_recurso_estado", table_name="asignacion_recurso")
    op.drop_table("asignacion_recurso")

    op.drop_table("detalle_solicitud_recurso")

    op.drop_index("ix_solicitud_recurso_solicitante", table_name="solicitud_recurso")
    op.drop_index("ix_solicitud_recurso_reserva", table_name="solicitud_recurso")
    op.drop_index("ix_solicitud_recurso_estado_creada", table_name="solicitud_recurso")
    op.drop_table("solicitud_recurso")

    op.drop_index("ix_recurso_tipo_estado", table_name="recurso")
    op.drop_index("ux_recurso_codigo_lower", table_name="recurso")
    op.drop_table("recurso")

    op.drop_index("ux_tipo_recurso_nombre_lower", table_name="tipo_recurso")
    op.drop_table("tipo_recurso")
