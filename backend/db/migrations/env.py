"""Environnement des migrations Alembic.

Deux façons de l'appeler :
- par le serveur (backend/db/database.py, init_db) : la connexion ouverte est passée dans
  config.attributes["connection"] ;
- en ligne de commande (`alembic upgrade head`…) : l'adresse est celle de DATABASE_URL (.env).
"""
from alembic import context
from sqlalchemy import create_engine

from backend.db.database import database_url
from backend.db.models import Base

target_metadata = Base.metadata


def run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite ne sait pas modifier une colonne : Alembic recrée alors la table (mode « batch »)
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    engine = create_engine(database_url())
    with engine.connect() as conn:
        run_migrations(conn)
    engine.dispose()
