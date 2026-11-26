"""Évaluations des agents IA par les joueurs, en fin de partie

Révision : 0006
Précédente : 0005
Date : 2026-11-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_ratings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("game_id", sa.Integer(), nullable=True),
        sa.Column("agent", sa.String(length=40), nullable=False),
        sa.Column("personality", sa.String(length=40), nullable=False),
        sa.Column("role", sa.Enum("reaper", "apothecary", "watchman", "medium", "inquisitor", "valet",
                                  name="rolekey", native_enum=False, length=20), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_ratings_user_id", "agent_ratings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_ratings_user_id", table_name="agent_ratings")
    op.drop_table("agent_ratings")
