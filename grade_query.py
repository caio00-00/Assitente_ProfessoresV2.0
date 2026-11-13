import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def run_grade_query():
    db = SessionLocal()
    try:
        print("\n=== QUERY 4: MAPEAMENTO DA TABELA GRADES ===")
        q4 = text("""
            SELECT
                turno_aula,
                horario_inicio,
                horario_fim,
                COUNT(*) as total
            FROM grades
            GROUP BY turno_aula, horario_inicio, horario_fim
            ORDER BY turno_aula, horario_inicio;
        """)
        res4 = db.execute(q4).fetchall()
        for row in res4:
            print(f"Turno Aula: {row[0]:<10} | Início: {row[1]} | Fim: {row[2]} | Total: {row[3]}")

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_grade_query()
