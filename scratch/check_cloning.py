import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.turma import Turma
from app.models.infraestrutura import GradeVersao
from app.models.auxiliares import Grade, Disciplina

db = SessionLocal()

print("--- CLONING INVESTIGATION ---")
# List turmas
turmas = db.query(Turma).all()
for t in turmas:
    versoes = db.query(GradeVersao).filter(GradeVersao.turma_id == t.id).all()
    # Only show turmas with grade versions
    if not versoes:
        continue
    print(f"\nTurma: {t.nome} (ID: {t.id}) | Ativa: {t.is_active}")
    print(f"  Versões de Grade ({len(versoes)}):")
    for v in versoes:
        slots = db.query(Grade).filter(Grade.grade_versao_id == v.id).all()
        print(f"    - Versão ID {v.id} | is_active={v.is_active} | data_ativacao={v.data_ativacao} | Slots: {len(slots)}")
        seen = set()
        duplicates = []
        for s in slots:
            # Let's query the discipline name
            disc = db.query(Disciplina).filter(Disciplina.id == s.disciplina_id).first()
            disc_name = disc.nome if disc else "N/A"
            key = (s.dia_semana, s.horario_inicio, s.horario_fim, s.disciplina_id)
            if key in seen:
                duplicates.append((s, disc_name))
            else:
                seen.add(key)
        if duplicates:
            print(f"      ⚠️ ENCONTRADOS {len(duplicates)} SLOTS DUPLICADOS nesta versão!")
            for d, name in duplicates:
                print(f"        Duplicado: Dia {d.dia_semana} | {d.horario_inicio}-{d.horario_fim} | Disciplina: {name} (ID: {d.disciplina_id})")

    # Check for slots associated with this turma but NOT linked to any version (grade_versao_id IS NULL)
    legacy_slots = db.query(Grade).filter(Grade.turma_id == t.id, Grade.grade_versao_id.is_(None)).all()
    if legacy_slots:
        print(f"  ⚠️ ENCONTRADOS {len(legacy_slots)} SLOTS LEGADOS (sem versão/versao_id IS NULL) associados a esta turma!")

db.close()
