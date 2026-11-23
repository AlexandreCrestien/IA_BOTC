"""Schéma initial : comptes, parties, succès

Révision : 0001
Précédente :
Date : 2026-11-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _enum(*values: str, name: str) -> sa.Enum:
    """Texte qui stocke la valeur de l'énumération (pas de type ENUM natif, identique sous SQLite et PostgreSQL)."""
    return sa.Enum(*values, name=name, native_enum=False, length=20)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pseudo", sa.String(length=20), nullable=False),
        sa.Column("pseudo_key", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=100), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pseudo_key"),
    )

    # user_id vide : partie anonymisée après la suppression de son compte
    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("role", _enum("reaper", "apothecary", "watchman", "medium", "inquisitor", "valet", name="rolekey"),
                  nullable=False),
        sa.Column("alignment", _enum("good", "evil", name="alignment"), nullable=False),
        sa.Column("turns", sa.Integer(), nullable=False),
        sa.Column("status", _enum("in_progress", "won", "lost", "abandoned", "interrupted", name="gamestatus"),
                  nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_games_status", "games", ["status"])
    op.create_index("ix_games_user_id", "games", ["user_id"])

    op.create_table(
        "unlocked_achievements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "code"),
    )
    op.create_index("ix_unlocked_achievements_user_id", "unlocked_achievements", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_unlocked_achievements_user_id", table_name="unlocked_achievements")
    op.drop_table("unlocked_achievements")
    op.drop_index("ix_games_user_id", table_name="games")
    op.drop_index("ix_games_status", table_name="games")
    op.drop_table("games")
    op.drop_table("users")
