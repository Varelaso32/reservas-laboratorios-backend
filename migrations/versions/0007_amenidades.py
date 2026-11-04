"""Amenidades: recursos instalados de forma fija en un espacio (HU-19 / HU-43).

Cada unidad de recurso puede quedar instalada como amenidad de un espacio. El
stock disponible descuenta esas unidades. El índice parcial garantiza que un
espacio no tenga dos unidades del mismo tipo instaladas.

Revision ID: 0007_amenidades
Revises: 0006_recursos
Create Date: 2026-11-03

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_amenidades"
down_revision: str | None = "0006_recursos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ux_recurso_amenidad",
        "recurso",
        ["espacio_id", "tipo_recurso_id"],
        unique=True,
        postgresql_where=sa.text("espacio_id IS NOT NULL AND activo"),
    )


def downgrade() -> None:
    op.drop_index("ux_recurso_amenidad", table_name="recurso")
