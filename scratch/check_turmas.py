import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("DATABASE_URL não encontrada no .env")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    print("=== TURMAS COUNT ===")
    count = conn.execute(text("SELECT COUNT(*) FROM turmas")).scalar()
    print("Total turmas:", count)

    print("\n=== EJA / QP TURMAS ===")
    result = conn.execute(text("SELECT id, nome, nomenclatura_padrao, serie_modulo, turno, is_active FROM turmas WHERE nome ILIKE '%EJA%' OR nome ILIKE '%QP%' OR nomenclatura_padrao ILIKE '%EJA%' OR nomenclatura_padrao ILIKE '%QP%'"))
    for r in result.fetchall():
        print(f"ID: {r[0]} | Nome: {r[1]} | Nomenclatura: {r[2]} | Série/Módulo: {r[3]} | Turno: {r[4]} | Ativa: {r[5]}")
