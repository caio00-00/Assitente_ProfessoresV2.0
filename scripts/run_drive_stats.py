import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def run_diagnostics():
    db = SessionLocal()
    try:
        # 4. Visão geral dos links
        print("\n=== QUERY 4: VISÃO GERAL DOS LINKS ===")
        q4_1 = text("""
            SELECT
                COUNT(*) as total_reports,
                COUNT(video_link) as com_video_link,
                COUNT(slide_link) as com_slide_link,
                COUNT(youtube_link) as com_youtube_link,
                COUNT(CASE WHEN video_link IS NULL
                          AND slide_link IS NULL
                          AND youtube_link IS NULL
                          THEN 1 END) as sem_nenhum_link
            FROM class_reports
            WHERE is_deleted = false;
        """)
        res4_1 = db.execute(q4_1).fetchone()
        print(f"Total Reports: {res4_1[0]}")
        print(f"Com Video Link: {res4_1[1]}")
        print(f"Com Slide Link: {res4_1[2]}")
        print(f"Com Youtube Link: {res4_1[3]}")
        print(f"Sem Nenhum Link: {res4_1[4]}")

        print("\n=== QUERY 4.2: LINKS POR STATUS ===")
        q4_2 = text("""
            SELECT
                status,
                COUNT(*) as total,
                COUNT(video_link) as com_video_link,
                COUNT(slide_link) as com_slide_link,
                COUNT(youtube_link) as com_youtube_link
            FROM class_reports
            WHERE is_deleted = false
            GROUP BY status
            ORDER BY status;
        """)
        res4_2 = db.execute(q4_2).fetchall()
        for row in res4_2:
            print(f"Status: {row[0]:<12} | Total: {row[1]:<5} | Video: {row[2]:<5} | Slide: {row[3]:<5} | Youtube: {row[4]}")

        # 5. Pasta do Drive (como é propriedade, não tem no SQL, mas vou listar por turma para ver se algum tem link manual?)
        # Na verdade, o usuário perguntou sobre video_folder_link no SQL. 
        # Vou reportar que não existe a coluna.

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_diagnostics()
