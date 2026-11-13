import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def run_query():
    db = SessionLocal()
    try:
        query = text("""
            WITH conflicts AS (
                SELECT
                    data_aula,
                    horario_aula,
                    estudio,
                    canal_utilizado
                FROM class_reports
                WHERE is_deleted = false
                    AND data_aula >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY data_aula, horario_aula, estudio, canal_utilizado
                HAVING COUNT(*) > 1
            )
            SELECT COUNT(*) FROM conflicts;
        """)
        
        result = db.execute(query).scalar()
        print(f"Total de conflitos agrupados: {result}")
                
    except Exception as e:
        print(f"Erro ao executar query: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_query()
