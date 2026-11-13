import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from app.models.class_report import ClassReport
from datetime import date

def query_conflict():
    db = SessionLocal()
    try:
        data_alvo = date(2026, 5, 7)
        estudio_alvo = "Estúdio 03"
        
        print(f"\n--- Relatórios Registrados no {estudio_alvo} para o dia {data_alvo.strftime('%d/%m/%Y')} ---")
        
        reports = db.query(ClassReport).filter(
            ClassReport.data_aula == data_alvo,
            ClassReport.estudio == estudio_alvo,
            ClassReport.is_deleted == False
        ).all()
        
        if not reports:
            print("Nenhum relatório encontrado.")
        
        for r in sorted(reports, key=lambda x: str(x.start_time)):
            horario = f"{r.start_time.strftime('%H:%M') if r.start_time else '?'} às {r.end_time.strftime('%H:%M') if r.end_time else '?'}"
            print(f"ID: {r.id}")
            print(f"Turma: {r.turma_nome}")
            print(f"Disciplina: {r.disciplina_nome}")
            print(f"Horário Salvo: {horario} (Campo Horário Aula: {r.horario_aula})")
            print(f"Status: {r.status}")
            print("-" * 50)
            
    finally:
        db.close()

if __name__ == "__main__":
    query_conflict()
