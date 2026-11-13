"""Script de diagnóstico — verifica diretores, professores e disciplinas no banco."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.DATABASE_URL)

with engine.connect() as conn:
    print("=" * 60)
    print("1. DIRETORES DE IMAGEM (todos, incluindo inativos)")
    print("=" * 60)
    rows = conn.execute(text("SELECT id, nome, is_active FROM diretores_imagem ORDER BY nome")).fetchall()
    if rows:
        for r in rows:
            status = "✅ ATIVO" if r.is_active else "❌ INATIVO"
            print(f"  {status}  |  {r.nome}  |  id: {r.id}")
    else:
        print("  ⚠️  NENHUM REGISTRO ENCONTRADO NA TABELA diretores_imagem")
    print(f"  Total: {len(rows)}")

    print()
    print("=" * 60)
    print("2. PROFESSORES (todos, incluindo inativos)")
    print("=" * 60)
    rows = conn.execute(text("SELECT id, nome, is_active FROM professores ORDER BY nome")).fetchall()
    if rows:
        for r in rows:
            status = "✅ ATIVO" if r.is_active else "❌ INATIVO"
            print(f"  {status}  |  {r.nome}  |  id: {r.id}")
    else:
        print("  ⚠️  NENHUM REGISTRO ENCONTRADO NA TABELA professores")
    print(f"  Total: {len(rows)}")

    print()
    print("=" * 60)
    print("3. DISCIPLINAS (todas, incluindo inativas)")
    print("=" * 60)
    rows = conn.execute(text("SELECT id, nome, is_active FROM disciplinas ORDER BY nome")).fetchall()
    if rows:
        for r in rows:
            status = "✅ ATIVA" if r.is_active else "❌ INATIVA"
            print(f"  {status}  |  {r.nome}  |  id: {r.id}")
    else:
        print("  ⚠️  NENHUM REGISTRO ENCONTRADO NA TABELA disciplinas")
    print(f"  Total: {len(rows)}")

    print()
    print("=" * 60)
    print("4. VÍNCULOS PROFESSOR ↔ DISCIPLINA (professor_disciplinas)")
    print("=" * 60)
    rows = conn.execute(text("""
        SELECT p.nome AS professor, d.nome AS disciplina
        FROM professor_disciplinas pd
        JOIN professores p ON pd.professor_id = p.id
        JOIN disciplinas d ON pd.disciplina_id = d.id
        ORDER BY p.nome, d.nome
    """)).fetchall()
    if rows:
        for r in rows:
            print(f"  {r.professor}  →  {r.disciplina}")
    else:
        print("  ⚠️  NENHUM VÍNCULO ENCONTRADO")
    print(f"  Total vínculos: {len(rows)}")
