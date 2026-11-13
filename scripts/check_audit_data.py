import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    q = text("""
        SELECT COUNT(*) as total_finalizado 
        FROM class_reports 
        WHERE is_deleted = false 
          AND status = 'FINALIZADO' 
          AND data_aula BETWEEN '2026-05-01' AND '2026-05-09'
    """)
    res = db.execute(q).fetchone()
    print(f"Total Finalizados: {res[0]}")
except Exception as e:
    print(f"Erro: {e}")
finally:
    db.close()
