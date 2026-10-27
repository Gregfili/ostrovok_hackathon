"""Схема счетов, фактов, броней и FAQ.

Revision ID: c4a8e1b07d22
Revises:
Create Date: 2026-10-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4a8e1b07d22"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "facts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("hotel_id", sa.Text(), nullable=False),
        sa.Column("feature", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("hotel_id", sa.Text(), nullable=True),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("hotel_id", sa.Text(), nullable=False),
        sa.Column("guest_id", sa.Text(), nullable=True),
        sa.Column("author_role", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "hotel_registrations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("hotel_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("account_id"),
    )
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("guest_id", sa.Text(), nullable=False),
        sa.Column("hotel_id", sa.Text(), nullable=False),
        sa.Column("check_in", sa.Text(), nullable=False),
        sa.Column("check_out", sa.Text(), nullable=False),
        sa.Column("nights", sa.Integer(), nullable=False),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "hotel_faq_config",
        sa.Column("hotel_id", sa.Text(), primary_key=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sections_json", sa.Text(), nullable=False, server_default="'{}'"),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "hotel_faq_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("hotel_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("uploaded_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "hotel_faq_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("hotel_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("hotel_faq_chunks")
    op.drop_table("hotel_faq_documents")
    op.drop_table("hotel_faq_config")
    op.drop_table("bookings")
    op.drop_table("hotel_registrations")
    op.drop_table("messages")
    op.drop_table("accounts")
    op.drop_table("facts")
