import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def run_diagnostics():
    db = SessionLocal()
    try:
        print("\n=== QUERY 1: STATUS DE COMPLIANCE GERAL ===")
        q1 = text("""
            SELECT status_compliance, COUNT(*)
            FROM class_reports
            WHERE is_deleted = false
            GROUP BY status_compliance;
        """)
        res1 = db.execute(q1).fetchall()
        for row in res1:
            print(f"Status: {row[0]:<12} | Total: {row[1]}")

        print("\n=== QUERY 2: SEM PDF, COM VÍDEO ===")
        q2 = text("""
            SELECT COUNT(*) as sem_pdf_com_video
            FROM class_reports
            WHERE is_deleted = false
              AND status = 'FINALIZADO'
              AND video_link IS NOT NULL
              AND slide_link IS NULL;
        """)
        res2 = db.execute(q2).fetchone()
        print(f"Sem PDF, com Vídeo: {res2[0]}")

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_diagnostics()
