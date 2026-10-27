"""Флаги скрытия сообщения у гостя и у отельера.

Revision ID: e6b1c4a90d33
Revises: c4a8e1b07d22
Create Date: 2026-10-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6b1c4a90d33"
down_revision: Union[str, Sequence[str], None] = "c4a8e1b07d22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("hidden_for_guest", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "messages",
        sa.Column("hidden_for_hotelier", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("messages", "hidden_for_hotelier")
    op.drop_column("messages", "hidden_for_guest")
