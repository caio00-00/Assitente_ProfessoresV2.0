"""
Canal Educação v3.0 — Configuração do banco de dados PostgreSQL.
Usa a Settings centralizada para obter a DATABASE_URL.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import get_settings

settings = get_settings()

if settings.eh_vercel:
    # v4.1: na Vercel cada instância da função vive pouco e pode haver muitas ao
    # mesmo tempo; pool próprio só seguraria conexões abertas no Supabase.
    # Sem pool, quem segura as conexões é o pooler do Supabase (porta 6543).
    from sqlalchemy.pool import NullPool

    engine = create_engine(settings.DATABASE_URL, poolclass=NullPool, pool_pre_ping=True)
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=300,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency injection: fornece uma sessão do banco por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
