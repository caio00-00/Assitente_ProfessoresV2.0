import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

try:
    from app.core.database import Base
except ImportError:
    from core.database import Base

from app.models import user, turma, class_report
from app.models import infraestrutura
from app.models.auxiliares import Grade, Unit, Professor, Disciplina, ProfessorDisciplina
from app.models import diretor_imagem, image_director_report

target_metadata = Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # v4: mesma URL da aplicação (respeita DATABASE_URL e POSTGRES_PORT; antes a
    # porta era fixa em 5432, o que impedia usar o pooler do Supabase).
    from app.core.config import get_settings

    database_url = os.environ.get("DATABASE_URL") or get_settings().DATABASE_URL

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
