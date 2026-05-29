"""
Shared database engine.

Local development uses a SQLite file. Production uses a hosted Postgres
database when DATABASE_URL is provided. The same code path serves both so
the app and dashboard never need to know which one is in use.
"""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from config import DATABASE_FILE, DATABASE_URL


_engine: Engine | None = None


def _resolve_connection_url() -> str:
    """Return the SQLAlchemy connection URL for the active environment."""
    if DATABASE_URL:
        url = DATABASE_URL
        # Hosts like Render/Heroku hand out "postgres://" which SQLAlchemy
        # needs spelled out with an explicit driver.
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url
    return f"sqlite:///{DATABASE_FILE}"


def get_engine() -> Engine:
    """Return a shared, lazily-created SQLAlchemy engine."""
    global _engine
    if _engine is None:
        connection_url = _resolve_connection_url()
        connect_args = {}
        if connection_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        _engine = create_engine(
            connection_url,
            pool_pre_ping=True,
            connect_args=connect_args,
            future=True,
        )
    return _engine


def is_postgres() -> bool:
    """True when the active database is Postgres."""
    return get_engine().dialect.name == "postgresql"
