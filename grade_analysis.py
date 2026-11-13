import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def run_grade_query():
    db = SessionLocal()
    try:
        print("\n=== QUERY 4: ANÁLISE DA TABELA GRADES ===")
        q4 = text("""
            SELECT
                dia_semana,
                horario_inicio,
                horario_fim,
                horario_aula,
                COUNT(*) as total
            FROM grades
            WHERE horario_aula IS NOT NULL
            GROUP BY dia_semana, horario_inicio, horario_fim, horario_aula
            ORDER BY horario_inicio, dia_semana;
        """)
        res4 = db.execute(q4).fetchall()
        for row in res4:
            print(f"Dia: {row[0]:<10} | Início: {row[1]} | Fim: {row[2]} | Horário Aula: {row[3]} | Total: {row[4]}")

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_grade_query()
