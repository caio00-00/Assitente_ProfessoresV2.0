import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.models.turma import Turma
from app.models.infraestrutura import GradeVersao
from app.models.auxiliares import Grade, Disciplina

db = SessionLocal()

print("--- SEARCHING SOURCE CLASS FOR TESTE OK ---")
# Get slots of teste ok (excluding id)
teste_ok = db.query(Turma).filter(Turma.nome == "teste ok").first()
if not teste_ok:
    print("teste ok not found")
    sys.exit()

v_teste_ok = db.query(GradeVersao).filter(GradeVersao.turma_id == teste_ok.id).first()
slots_teste_ok = db.query(Grade).filter(Grade.grade_versao_id == v_teste_ok.id).all()

teste_slots_set = {(s.dia_semana, s.horario_inicio, s.horario_fim, s.disciplina_id) for s in slots_teste_ok}

turmas = db.query(Turma).filter(Turma.id != teste_ok.id).all()
for t in turmas:
    versoes = db.query(GradeVersao).filter(GradeVersao.turma_id == t.id).all()
    for v in versoes:
        slots = db.query(Grade).filter(Grade.grade_versao_id == v.id).all()
        slots_set = {(s.dia_semana, s.horario_inicio, s.horario_fim, s.disciplina_id) for s in slots}
        # Check intersection size
        intersection = teste_slots_set.intersection(slots_set)
        if len(intersection) > 15: # High match
            print(f"Match found! Turma: {t.nome} (ID: {t.id}) | Versão ID: {v.id} | Match slots: {len(intersection)}/{len(teste_slots_set)}")
            # Show if this source version has duplicates too
            seen = set()
            duplicates = []
            for s in slots:
                key = (s.dia_semana, s.horario_inicio, s.horario_fim, s.disciplina_id)
                if key in seen:
                    duplicates.append(s)
                else:
                    seen.add(key)
            print(f"  Source version has {len(duplicates)} duplicate slots.")

db.close()
