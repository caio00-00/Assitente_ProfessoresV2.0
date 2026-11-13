import os
import sys
from datetime import date
from sqlalchemy.orm import Session

sys.path.append("/app")

from app.core.database import SessionLocal
from app.models.class_report import ClassReport

def investigate_report():
    db = SessionLocal()
    try:
        report_id = "7d50d9a0-10b1-4657-b516-c142ca57c7c5"
        r = db.query(ClassReport).filter(ClassReport.id == report_id).first()

        if r:
            print(f"\n--- Detalhes do Relatório Conflitante ---")
            print(f"ID: {r.id}")
            print(f"Data: {r.data_aula}")
            print(f"Estúdio: {r.estudio}")
            print(f"Horário: {r.start_time} - {r.end_time}")
            print(f"Status: {r.status}")
            print(f"Turma: {r.turma_nome}")
            print(f"Disciplina: {r.disciplina_nome}")
            print(f"Deletado: {r.is_deleted}")
            
            # Agora buscar outros no mesmo dia e estúdio
            others = db.query(ClassReport).filter(
                ClassReport.data_aula == r.data_aula,
                ClassReport.estudio == r.estudio,
                ClassReport.is_deleted == False
            ).all()
            
            print(f"\n--- Outros relatórios no Estúdio {r.estudio} em {r.data_aula} ---")
            for o in others:
                print(f"{o.id} | {o.start_time} - {o.end_time} | {o.status} | {o.turma_nome}")

        else:
            print(f"Relatório {report_id} não encontrado.")

    finally:
        db.close()

if __name__ == "__main__":
    investigate_report()
