"""
Cria usuários + diretores_imagem a partir de data/import/diretores_imagem_povoamento.csv

Uso Dokploy:
  python scripts/seed_diretores_imagem_hml.py --dry-run
  python scripts/seed_diretores_imagem_hml.py --apply
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.diretor_imagem import DiretorImagem
from app.models.user import User

DEFAULT_CSV = Path("data/import/diretores_imagem_povoamento.csv")


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            rows.append(row)
    return rows


def seed_row(db, row: dict, dry_run: bool) -> str:
    nome = (row.get("nome_cadastro") or "").strip().upper()
    email = (row.get("email_ficticio") or "").strip().lower()
    senha = row.get("senha_inicial") or "Trocar@123"
    if not nome or not email:
        return "skip_invalido"

    existing_dir = db.query(DiretorImagem).filter(DiretorImagem.nome == nome).first()
    if existing_dir:
        if existing_dir.user_id:
            return "skip_diretor_existe"
        # vincular user se diretor existe sem login
        user = db.query(User).filter(User.email == email).first()
        if not user:
            if dry_run:
                return "would_link_user"
            user = User(
                id=uuid.uuid4(),
                email=email,
                full_name=nome.title(),
                role="diretor_imagem",
                hashed_password=get_password_hash(senha),
                email_confirmed=True,
                is_active=True,
            )
            db.add(user)
            db.flush()
        existing_dir.user_id = user.id
        return "linked_user"

    if db.query(User).filter(User.email == email).first():
        return "skip_email_existe"

    if dry_run:
        return "would_insert"

    user = User(
        id=uuid.UUID(row["user_id"]) if row.get("user_id") else uuid.uuid4(),
        email=email,
        full_name=nome.title(),
        role="diretor_imagem",
        hashed_password=get_password_hash(senha),
        email_confirmed=True,
        is_active=True,
    )
    diretor = DiretorImagem(
        id=uuid.UUID(row["diretor_imagem_id"]) if row.get("diretor_imagem_id") else uuid.uuid4(),
        nome=nome,
        is_active=True,
        user_id=user.id,
    )
    db.add(user)
    db.add(diretor)
    return "inserted"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    args = parser.parse_args()
    dry_run = not args.apply or args.dry_run

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        raise SystemExit(f"CSV não encontrado: {csv_path}")

    rows = load_rows(csv_path)
    stats: dict = {}
    db = SessionLocal()
    try:
        for row in rows:
            result = seed_row(db, row, dry_run=dry_run)
            stats[result] = stats.get(result, 0) + 1
        if dry_run:
            db.rollback()
            print("Dry-run (rollback).")
        else:
            db.commit()
            print("Commit OK.")
        print("Stats:", stats)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
