import os
import sys
from datetime import date
from sqlalchemy.orm import Session

# Adicionar /app ao sys.path
sys.path.append("/app")

from app.core.database import SessionLocal
from app.models.class_report import ClassReport

def list_reports():
    db = SessionLocal()
    try:
        today = date(2026, 5, 7) # Data fixa para o teste conforme metadados
        reports = db.query(ClassReport).filter(
            ClassReport.data_aula == today,
            ClassReport.is_deleted == False
        ).order_by(ClassReport.estudio, ClassReport.start_time).all()

        print(f"\n--- Relatórios de Aula para {today} ---")
        print(f"{'ID':<38} | {'Estúdio':<12} | {'Horário':<15} | {'Status':<12} | {'Turma':<25} | {'Disciplina'}")
        print("-" * 130)

        for r in reports:
            horario = f"{r.start_time.strftime('%H:%M')} - {r.end_time.strftime('%H:%M')}" if r.start_time and r.end_time else "SEM HORA"
            turma_nome = r.turma_nome
            disciplina_nome = r.disciplina_nome
            print(f"{str(r.id):<38} | {r.estudio:<12} | {horario:<15} | {r.status:<12} | {turma_nome[:25]:<25} | {disciplina_nome}")

    finally:
        db.close()

if __name__ == "__main__":
    list_reports()
