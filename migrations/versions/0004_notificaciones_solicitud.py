"""Notificaciones del estado de las solicitudes.

La campana deja de avisar solo cesiones: ahora también avisa al solicitante en
qué quedó su solicitud (pendiente, aprobada o rechazada con motivo) y a los
revisores lo que tienen por decidir (HU-10, HU-11, HU-35).

Revision ID: 0004_notificaciones_solicitud
Revises: 0003_cesion_notificaciones
Create Date: 2026-10-29

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004_notificaciones_solicitud"
down_revision: str | None = "0003_cesion_notificaciones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_notificacion_tipo_notificacion"

TIPOS_ANTIGUOS = (
    "CESION_SOLICITADA",
    "CESION_ACEPTADA",
    "CESION_RECHAZADA",
    "CESION_CONFIRMADA",
)
TIPOS_NUEVOS = TIPOS_ANTIGUOS + (
    "SOLICITUD_RECIBIDA",
    "SOLICITUD_PENDIENTE",
    "SOLICITUD_APROBADA",
    "SOLICITUD_RECHAZADA",
    "SOLICITUD_POR_AUTORIZAR",
    "AUTORIZACION_CONCEDIDA",
    "AUTORIZACION_DENEGADA",
)


def _check(valores: tuple[str, ...]) -> str:
    lista = ", ".join(f"'{valor}'" for valor in valores)
    return f"ALTER TABLE notificacion ADD CONSTRAINT {CONSTRAINT} CHECK (tipo IN ({lista}))"


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "notificacion", type_="check")
    op.execute(_check(TIPOS_NUEVOS))


def downgrade() -> None:
    # Sin esto el CHECK nuevo no se puede quitar: habría filas con tipos no permitidos
    lista = ", ".join(f"'{valor}'" for valor in TIPOS_NUEVOS[len(TIPOS_ANTIGUOS) :])
    op.execute(f"DELETE FROM notificacion WHERE tipo IN ({lista})")
    op.drop_constraint(op.f(CONSTRAINT), "notificacion", type_="check")
    op.execute(_check(TIPOS_ANTIGUOS))
