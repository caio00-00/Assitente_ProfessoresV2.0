import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def run_query():
    db = SessionLocal()
    try:
        query = text("""
            SELECT DISTINCT
                horario_aula,
                turno,
                start_time,
                end_time,
                COUNT(*) as total
            FROM class_reports
            WHERE is_deleted = false
                AND start_time IS NOT NULL
                AND end_time IS NOT NULL
            GROUP BY horario_aula, turno, start_time, end_time
            ORDER BY turno, horario_aula, start_time;
        """)
        
        result = db.execute(query).fetchall()
        
        print("\n=== MAPEAMENTO HORÁRIO_AULA -> START/END TIME ===")
        print(f"{'Horário Aula':<20} | {'Turno':<10} | {'Início':<10} | {'Fim':<10} | {'Total'}")
        print("-" * 70)
        for row in result:
            print(f"{str(row[0]):<20} | {str(row[1]):<10} | {str(row[2]):<10} | {str(row[3]):<10} | {row[4]}")
                
    except Exception as e:
        print(f"Erro ao executar query: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_query()
