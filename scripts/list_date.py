import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from app.models.class_report import ClassReport
from datetime import date

def list_by_date():
    db = SessionLocal()
    try:
        target_date = date(2026, 4, 22)
        reports = db.query(ClassReport).filter(ClassReport.data_aula == target_date).all()
        print(f"\n--- Relatórios para {target_date} ---")
        for r in reports:
            print(f"{r.id} | {r.estudio} | {r.start_time} - {r.end_time} | {r.status} | {r.turma_nome} | {r.disciplina_nome}")
    finally:
        db.close()

if __name__ == "__main__":
    list_by_date()
