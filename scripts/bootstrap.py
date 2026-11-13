"""
Canal Educacao v3.0 — Bootstrap do banco de dados.
Cria todas as tabelas e o usuario admin inicial.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import engine, SessionLocal, Base
from app.models.user import User
from app.core.security import get_password_hash

# Importa todos os models para que o Base.metadata os reconheca
import app.models.turma  # noqa: F401
import app.models.auxiliares  # noqa: F401
import app.models.class_report  # noqa: F401
import app.models.audit_log  # noqa: F401


def bootstrap():
    print("Criando tabelas no banco de dados...")
    Base.metadata.create_all(bind=engine)
    print("Tabelas criadas com sucesso.")

    db = SessionLocal()
    try:
        email = "admin@canaleducacao.com"
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"Admin {email} ja existe. Pulando criacao.")
            return

        admin_user = User(
            email=email,
            hashed_password=get_password_hash("admin123"),
            full_name="Admin",
            is_active=True,
            role="admin",
            email_confirmed=True,
        )
        db.add(admin_user)
        db.commit()
        print(f"Admin criado com sucesso! Email: {email} | Senha: admin123")
    finally:
        db.close()


if __name__ == "__main__":
    bootstrap()
