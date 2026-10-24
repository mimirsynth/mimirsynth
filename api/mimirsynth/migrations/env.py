"""Entorno de Alembic: usa el engine de la app (o la URL de alembic.ini en desarrollo) y los modelos del plano de control.

El índice de texto (`episode_chunks`) NO se gestiona aquí: es una caché reconstruible desde FalkorDB y la crea `index.init_index`.
"""
from alembic import context

from mimirsynth import models  # noqa: F401  (registra los modelos en Base.metadata)
from mimirsynth.store import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    conn = config.attributes.get("connection")
    if conn is None:
        from sqlalchemy import create_engine
        with create_engine(config.get_main_option("sqlalchemy.url")).connect() as c:
            _run(c)
    else:
        _run(conn)


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True, render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
