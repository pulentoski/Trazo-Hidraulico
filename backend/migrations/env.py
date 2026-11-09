from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.core.db import Base
import app.models  # noqa: F401  (registra los modelos)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # Tablas propias de PostGIS/tiger no se gestionan aquí.
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True


def run_migrations_online() -> None:
    url = config.attributes.get("url") or get_settings().database_url
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
