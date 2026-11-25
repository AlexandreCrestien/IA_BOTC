"""Signalements des messages des agents IA par les joueurs

Révision : 0005
Précédente : 0004
Date : 2026-11-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("game_id", sa.Integer(), nullable=True),
        sa.Column("agent", sa.String(length=40), nullable=False),
        sa.Column("personality", sa.String(length=40), nullable=False),
        sa.Column("role", sa.Enum("reaper", "apothecary", "watchman", "medium", "inquisitor", "valet",
                                  name="rolekey", native_enum=False, length=20), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("moment", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_reports_user_id", "agent_reports", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_reports_user_id", table_name="agent_reports")
    op.drop_table("agent_reports")
