import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def run_diagnostics():
    db = SessionLocal()
    try:
        print("\n=== QUERY: ANÁLISE DE LINKS (VÍDEO vs SLIDE) ===")
        q = text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN video_link IS NOT NULL 
                          AND slide_link IS NULL THEN 1 END) as tem_video_sem_pdf,
                COUNT(CASE WHEN video_link IS NULL 
                          AND slide_link IS NOT NULL THEN 1 END) as tem_pdf_sem_video,
                COUNT(CASE WHEN video_link IS NOT NULL 
                          AND slide_link IS NOT NULL THEN 1 END) as tem_ambos,
                COUNT(CASE WHEN video_link IS NULL 
                          AND slide_link IS NULL THEN 1 END) as sem_ambos
            FROM class_reports
            WHERE is_deleted = false
                AND status = 'FINALIZADO';
        """)
        res = db.execute(q).fetchone()
        print(f"Total Finalizados: {res[0]}")
        print(f"Tem Vídeo SEM PDF: {res[1]}")
        print(f"Tem PDF SEM Vídeo: {res[2]}")
        print(f"Tem AMBOS: {res[3]}")
        print(f"SEM AMBOS: {res[4]}")

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_diagnostics()
