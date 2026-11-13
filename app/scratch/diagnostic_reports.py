import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from app.models.class_report import ClassReport
from app.models.turma import Turma
from app.models.auxiliares import Disciplina

def run():
    db = SessionLocal()
    try:
        reports = db.query(ClassReport).filter(
            ClassReport.is_deleted == False
        ).order_by(ClassReport.created_at.desc()).limit(10).all()
        
        print("\n=== ULTIMOS 10 RELATORIOS ===")
        for r in reports:
            t = db.query(Turma).filter(Turma.id == r.turma_id).first()
            d = db.query(Disciplina).filter(Disciplina.id == r.disciplina_id).first()
            t_nome = t.nome if t else "N/A"
            d_nome = d.nome if d else "N/A"
            print(f"ID: {r.id} | Data: {r.data_aula} | Horário: {r.horario_aula} | Status: {r.status} | Turma: {t_nome} | Disciplina: {d_nome}")
    finally:
        db.close()

if __name__ == "__main__":
    run()
