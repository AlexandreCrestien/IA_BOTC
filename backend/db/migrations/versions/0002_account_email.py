"""Adresse e-mail des comptes, liens « mot de passe oublié », avertissement avant suppression

Révision : 0002
Précédente : 0001
Date : 2026-11-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Colonne facultative pour la base : les comptes déjà créés n'ont pas d'adresse.
    # L'adresse est obligatoire à l'inscription (règle vérifiée par l'application).
    # batch_alter_table : sous SQLite, la table est recréée (ALTER TABLE y est limité) ; sous PostgreSQL, ALTER direct.
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=254), nullable=True))
        batch_op.add_column(sa.Column("inactivity_warned_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint("uq_users_email", ["email"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_email", type_="unique")
        batch_op.drop_column("inactivity_warned_at")
        batch_op.drop_column("email")
