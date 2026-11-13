import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from app.models.class_report import ClassReport
from datetime import date

def list_today():
    db = SessionLocal()
    try:
        today = date(2026, 5, 7)
        reports = db.query(ClassReport).filter(
            ClassReport.data_aula == today,
            ClassReport.is_deleted == False,
            ClassReport.status != "CANCELADO"
        ).all()
        print(f"\n--- Relatórios Ativos para {today} ---")
        if not reports:
            print("Nenhum relatório encontrado para hoje.")
        for r in reports:
            print(f"{r.id} | {r.estudio} | {r.start_time} - {r.end_time} | {r.status} | {r.turma_nome} | {r.disciplina_nome}")
    finally:
        db.close()

if __name__ == "__main__":
    list_today()
