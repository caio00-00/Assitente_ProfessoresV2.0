import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.models.turma import Turma
from app.models.infraestrutura import GradeVersao
from app.models.auxiliares import Grade, Disciplina

db = SessionLocal()

print("--- ALL LEGACY SLOTS (grade_versao_id IS NULL) ---")
legacy_slots = db.query(Grade).filter(Grade.grade_versao_id.is_(None)).all()
print(f"Total legacy slots found: {len(legacy_slots)}")
for s in legacy_slots:
    turma = db.query(Turma).filter(Turma.id == s.turma_id).first()
    turma_name = turma.nome if turma else "N/A"
    disc = db.query(Disciplina).filter(Disciplina.id == s.disciplina_id).first()
    disc_name = disc.nome if disc else "N/A"
    print(f"Slot ID: {s.id} | Turma: {turma_name} | Dia: {s.dia_semana} | {s.horario_inicio} às {s.horario_fim} | Disciplina: {disc_name}")

db.close()
