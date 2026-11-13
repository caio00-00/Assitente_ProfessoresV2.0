import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def run_query():
    db = SessionLocal()
    try:
        query = text("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN start_time IS NULL THEN 1 ELSE 0 END) as start_null,
                SUM(CASE WHEN end_time IS NULL THEN 1 ELSE 0 END) as end_null
            FROM class_reports
            WHERE is_deleted = false AND regular = 'Sim';
        """)
        
        result = db.execute(query).fetchone()
        print(f"Total Regular: {result[0]}")
        print(f"Start Time NULL: {result[1]}")
        print(f"End Time NULL: {result[2]}")
                
    except Exception as e:
        print(f"Erro ao executar query: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_query()
