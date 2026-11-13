import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from app.models.class_report import ClassReport
from datetime import time

def find_by_time():
    db = SessionLocal()
    try:
        t_start = time(9, 50)
        reports = db.query(ClassReport).filter(ClassReport.start_time == t_start).all()
        print(f"\n--- Relatórios começando às 09:50 ---")
        for r in reports:
            print(f"{r.id} | {r.data_aula} | {r.estudio} | {r.start_time} - {r.end_time} | {r.status} | {r.turma_nome}")
    finally:
        db.close()

if __name__ == "__main__":
    find_by_time()
