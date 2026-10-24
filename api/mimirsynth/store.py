"""Plano de control (usuarios, brains, roles, auditoría) en SQL: PostgreSQL en producción, SQLite en desarrollo."""
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base


@lru_cache
def engine():
    kw = {"connect_args": {"check_same_thread": False}} if settings.database_url.startswith("sqlite") else {"pool_pre_ping": True}
    return create_engine(settings.database_url, **kw)


@lru_cache
def _factory():
    return sessionmaker(bind=engine(), expire_on_commit=False)


def _add_missing_columns() -> None:
    """Migración mínima y aditiva: añade a tablas existentes las columnas nuevas del modelo (sustituir por Alembic antes de publicar)."""
    from sqlalchemy import inspect, text
    eng = engine()
    insp = inspect(eng)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in have:
                ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(dialect=eng.dialect)}'
                if col.default is not None and not callable(getattr(col.default, "arg", None)) and col.default.arg is not None:
                    d = col.default.arg
                    ddl += " DEFAULT " + (f"'{d}'" if isinstance(d, str) else str(d).lower())
                with eng.begin() as c:
                    c.execute(text(ddl))


def init_db() -> None:
    """Aplica las migraciones de Alembic. Una BD anterior a Alembic (creada con create_all) se lleva primero a la forma de la
    línea base con la migración aditiva y se marca como 0001; una BD nueva se crea entera desde las migraciones."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    eng = engine()
    tables = set(inspect(eng).get_table_names())
    legacy = "alembic_version" not in tables and "users" in tables
    if legacy:
        _add_missing_columns()
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    with eng.connect() as conn:
        cfg.attributes["connection"] = conn
        if legacy:
            command.stamp(cfg, "0001")
        command.upgrade(cfg, "head")
        conn.commit()


def get_db():
    db: Session = _factory()()
    try:
        yield db
    finally:
        db.close()
