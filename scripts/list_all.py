import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from app.models.class_report import ClassReport

def list_last_reports():
    db = SessionLocal()
    try:
        reports = db.query(ClassReport).order_by(ClassReport.created_at.desc()).limit(20).all()
        print(f"\n--- Últimos 20 Relatórios ---")
        for r in reports:
            print(f"{r.id} | {r.data_aula} | {r.estudio} | {r.start_time} - {r.end_time} | {r.status} | {r.turma_nome}")
    finally:
        db.close()

if __name__ == "__main__":
    list_last_reports()
