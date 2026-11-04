"""Asistencia, no-show, strikes, sanciones y prioridad de solicitudes.

- HU-12: prioridad asociada a cada solicitud según el rol de reserva.
- HU-17: motivo de cancelación en la reserva.
- HU-38 / HU-39: estado de asistencia, inicio efectivo y aviso de no-show.
- HU-40 / HU-41: política de sanciones, strikes y bloqueo.
- HU-42: reactivaciones y justificaciones.

Revision ID: 0005_asistencia_strikes
Revises: 0004_notificaciones_solicitud
Create Date: 2026-10-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_asistencia_strikes"
down_revision: str | None = "0004_notificaciones_solicitud"
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
)


def _check(valores: tuple[str, ...]) -> str:
    lista = ", ".join(f"'{valor}'" for valor in valores)
    return f"({lista})"


def upgrade() -> None:
    # --- HU-12: prioridad de la solicitud --- #
    op.add_column(
        "solicitud",
        sa.Column("prioridad", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_solicitud_prioridad_valida"), "solicitud", "prioridad BETWEEN 0 AND 3"
    )
    op.execute(
        """
        UPDATE solicitud AS s
        SET prioridad = CASE u.cargo
            WHEN 'ESTUDIANTE' THEN 0
            WHEN 'DOCENTE' THEN 1
            WHEN 'ADMINISTRATIVO' THEN 1
            WHEN 'COORDINADOR_LABORATORIOS' THEN 2
            WHEN 'ADMINISTRADOR_SALA' THEN 2
            WHEN 'ADMINISTRADOR_SISTEMA' THEN 3
            ELSE 0
        END
        FROM usuario AS u
        WHERE u.id = s.solicitante_id
        """
    )

    # --- HU-17 / HU-38 / HU-39: datos de la reserva --- #
    op.add_column("reserva", sa.Column("motivo_cancelacion", sa.Text(), nullable=True))
    op.add_column(
        "reserva",
        sa.Column(
            "estado_asistencia",
            sa.String(length=30),
            server_default=sa.text("'PENDIENTE'"),
            nullable=False,
        ),
    )
    op.add_column(
        "reserva", sa.Column("inicio_efectivo", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "reserva",
        sa.Column(
            "advertencia_enviada",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "reserva",
        sa.Column(
            "sancionable", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    # Las reservas históricas no se sancionan al activar la funcionalidad
    op.execute("UPDATE reserva SET sancionable = false")
    op.create_check_constraint(
        op.f("ck_reserva_estado_asistencia"),
        "reserva",
        "estado_asistencia IN ('PENDIENTE', 'ASISTIO', 'NO_ASISTIO')",
    )
    op.create_index(
        "ix_reserva_asistencia", "reserva", ["estado", "estado_asistencia", "inicio"]
    )

    # El estado de la reserva ahora incluye el no-show (HU-39)
    op.drop_constraint(op.f("ck_reserva_estado_reserva"), "reserva", type_="check")
    op.create_check_constraint(
        op.f("ck_reserva_estado_reserva"),
        "reserva",
        "estado IN ('ACTIVA', 'CANCELADA', 'NO_ASISTIO')",
    )

    # Nuevas acciones del historial (HU-38 a HU-42)
    op.drop_constraint(op.f("ck_trazabilidad_accion_trazabilidad"), "trazabilidad", type_="check")
    op.create_check_constraint(
        op.f("ck_trazabilidad_accion_trazabilidad"),
        "trazabilidad",
        f"accion IN {_check(ACCIONES_TRAZABILIDAD)}",
    )

    # Nuevos tipos de notificación (HU-39 a HU-42)
    op.drop_constraint(op.f("ck_notificacion_tipo_notificacion"), "notificacion", type_="check")
    op.create_check_constraint(
        op.f("ck_notificacion_tipo_notificacion"),
        "notificacion",
        f"tipo IN {_check(TIPOS_NOTIFICACION)}",
    )

    # --- HU-41: política de tolerancia y sanciones --- #
    op.create_table(
        "parametro_sancion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tolerancia_minutos", sa.Integer(), server_default=sa.text("10"), nullable=False),
        sa.Column("aviso_minutos", sa.Integer(), server_default=sa.text("5"), nullable=False),
        sa.Column("minutos_por_strike", sa.Integer(), server_default=sa.text("10"), nullable=False),
        sa.Column("max_strikes", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column(
            "acciones",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actualizado_por"], ["usuario.id"], name=op.f("fk_parametro_sancion_actualizado_por_usuario")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parametro_sancion")),
        sa.CheckConstraint("tolerancia_minutos > 0", name=op.f("ck_parametro_sancion_tolerancia_positiva")),
        sa.CheckConstraint("aviso_minutos >= 0", name=op.f("ck_parametro_sancion_aviso_no_negativo")),
        sa.CheckConstraint(
            "aviso_minutos < tolerancia_minutos",
            name=op.f("ck_parametro_sancion_aviso_menor_que_tolerancia"),
        ),
        sa.CheckConstraint(
            "minutos_por_strike > 0", name=op.f("ck_parametro_sancion_minutos_strike_positivos")
        ),
        sa.CheckConstraint("max_strikes > 0", name=op.f("ck_parametro_sancion_max_strikes_positivo")),
    )
    op.execute(
        """
        INSERT INTO parametro_sancion
            (id, tolerancia_minutos, aviso_minutos, minutos_por_strike, max_strikes, acciones)
        VALUES (
            1, 10, 5, 10, 3,
            '[{"nivel": 1, "accion": "ADVERTENCIA"},
              {"nivel": 2, "accion": "ADVERTENCIA"},
              {"nivel": 3, "accion": "BLOQUEO"}]'::json
        )
        """
    )

    # --- HU-42: reactivaciones --- #
    op.create_table(
        "reactivacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=30),
            server_default=sa.text("'PENDIENTE'"),
            nullable=False,
        ),
        sa.Column("justificacion", sa.Text(), nullable=False),
        sa.Column("detalle", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("strikes_anulados", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("decidida_por", sa.Integer(), nullable=True),
        sa.Column("fecha_decision", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_rechazo", sa.Text(), nullable=True),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuario.id"], name=op.f("fk_reactivacion_usuario_id_usuario")
        ),
        sa.ForeignKeyConstraint(
            ["decidida_por"], ["usuario.id"], name=op.f("fk_reactivacion_decidida_por_usuario")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reactivacion")),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'ACEPTADA', 'RECHAZADA')",
            name=op.f("ck_reactivacion_estado_reactivacion"),
        ),
    )
    op.create_index(
        "ix_reactivacion_usuario_estado", "reactivacion", ["usuario_id", "estado"]
    )

    # --- HU-40: strikes --- #
    op.create_table(
        "strike",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("reserva_id", sa.Integer(), nullable=False),
        sa.Column("minutos_retraso", sa.Integer(), nullable=False),
        sa.Column("anulado", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("anulado_por", sa.Integer(), nullable=True),
        sa.Column("motivo_anulacion", sa.Text(), nullable=True),
        sa.Column("reactivacion_id", sa.Integer(), nullable=True),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name=op.f("fk_strike_usuario_id_usuario")),
        sa.ForeignKeyConstraint(["reserva_id"], ["reserva.id"], name=op.f("fk_strike_reserva_id_reserva")),
        sa.ForeignKeyConstraint(
            ["anulado_por"], ["usuario.id"], name=op.f("fk_strike_anulado_por_usuario")
        ),
        sa.ForeignKeyConstraint(
            ["reactivacion_id"], ["reactivacion.id"], name=op.f("fk_strike_reactivacion_id_reactivacion")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strike")),
        sa.CheckConstraint("minutos_retraso >= 0", name=op.f("ck_strike_minutos_no_negativos")),
    )
    op.create_index("ix_strike_usuario_anulado", "strike", ["usuario_id", "anulado"])
    op.create_index("ix_strike_reserva", "strike", ["reserva_id"])


def downgrade() -> None:
    op.drop_index("ix_strike_reserva", table_name="strike")
    op.drop_index("ix_strike_usuario_anulado", table_name="strike")
    op.drop_table("strike")
    op.drop_index("ix_reactivacion_usuario_estado", table_name="reactivacion")
    op.drop_table("reactivacion")
    op.drop_table("parametro_sancion")

    # Restaurar los CHECK anteriores
    op.drop_constraint(op.f("ck_notificacion_tipo_notificacion"), "notificacion", type_="check")
    tipos_antiguos = TIPOS_NOTIFICACION[:11]
    op.create_check_constraint(
        op.f("ck_notificacion_tipo_notificacion"),
        "notificacion",
        f"tipo IN {_check(tipos_antiguos)}",
    )
    op.drop_constraint(op.f("ck_trazabilidad_accion_trazabilidad"), "trazabilidad", type_="check")
    acciones_antiguas = ACCIONES_TRAZABILIDAD[:10]
    op.create_check_constraint(
        op.f("ck_trazabilidad_accion_trazabilidad"),
        "trazabilidad",
        f"accion IN {_check(acciones_antiguas)}",
    )
    op.drop_constraint(op.f("ck_reserva_estado_reserva"), "reserva", type_="check")
    op.create_check_constraint(
        op.f("ck_reserva_estado_reserva"),
        "reserva",
        "estado IN ('ACTIVA', 'CANCELADA')",
    )
    op.drop_index("ix_reserva_asistencia", table_name="reserva")
    op.drop_constraint(op.f("ck_reserva_estado_asistencia"), "reserva", type_="check")
    op.drop_column("reserva", "sancionable")
    op.drop_column("reserva", "advertencia_enviada")
    op.drop_column("reserva", "inicio_efectivo")
    op.drop_column("reserva", "estado_asistencia")
    op.drop_column("reserva", "motivo_cancelacion")

    op.drop_constraint(op.f("ck_solicitud_prioridad_valida"), "solicitud", type_="check")
    op.drop_column("solicitud", "prioridad")
