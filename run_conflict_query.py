import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text
import pandas as pd

def run_query():
    db = SessionLocal()
    try:
        query = text("""
            SELECT
                data_aula,
                horario_aula,
                estudio,
                canal_utilizado,
                COUNT(*) as total,
                STRING_AGG(disciplina.nome, ' × ') as disciplinas,
                STRING_AGG(turma.nome, ' × ') as turmas,
                STRING_AGG(status, ' × ') as status
            FROM class_reports
            LEFT JOIN disciplinas disciplina ON class_reports.disciplina_id = disciplina.id
            LEFT JOIN turmas turma ON class_reports.turma_id = turma.id
            WHERE is_deleted = false
                AND data_aula >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY data_aula, horario_aula, estudio, canal_utilizado
            HAVING COUNT(*) > 1
            ORDER BY data_aula DESC;
        """)
        
        result = db.execute(query).fetchall()
        
        print("\n=== RESULTADO DA QUERY DE CONFLITOS ===")
        if not result:
            print("Nenhum conflito encontrado na query.")
        else:
            for row in result:
                print(f"Data: {row[0]}")
                print(f"Horário: {row[1]}")
                print(f"Estúdio: {row[2]}")
                print(f"Canal: {row[3]}")
                print(f"Total: {row[4]}")
                print(f"Disciplinas: {row[5]}")
                print(f"Turmas: {row[6]}")
                print(f"Status: {row[7]}")
                print("-" * 50)
                
    except Exception as e:
        print(f"Erro ao executar query: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_query()
