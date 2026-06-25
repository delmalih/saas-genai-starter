"""add together ai provider

Revision ID: a1b2c3d4e5f6
Revises: 5404219f916c
Create Date: 2026-06-24 22:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "5404219f916c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "org_llm_settings", sa.Column("together_api_key_encrypted", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("org_llm_settings", "together_api_key_encrypted")
