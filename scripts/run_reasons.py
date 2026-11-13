import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def run_diagnostics():
    db = SessionLocal()
    try:
        q = text("""
            SELECT
                COUNT(CASE WHEN video_link IS NULL THEN 1 END) as sem_video,
                COUNT(CASE WHEN slide_link IS NULL THEN 1 END) as sem_pdf
            FROM class_reports
            WHERE is_deleted = false
              AND status_compliance = 'Pendente'
              AND status = 'FINALIZADO';
        """)
        res = db.execute(q).fetchone()
        print(f"Sem video: {res[0]}")
        print(f"Sem PDF: {res[1]}")
    except Exception as e:
        print(f"Erro: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_diagnostics()
