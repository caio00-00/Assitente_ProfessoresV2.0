import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.models.turma import Turma
from app.models.infraestrutura import GradeVersao
from app.models.auxiliares import Grade, Disciplina

db = SessionLocal()

print("--- DETAILED SLOTS FOR TESTE OK ---")
teste_ok = db.query(Turma).filter(Turma.nome == "teste ok").first()
if teste_ok:
    print(f"Turma 'teste ok' ID: {teste_ok.id}")
    versoes = db.query(GradeVersao).filter(GradeVersao.turma_id == teste_ok.id).all()
    for v in versoes:
        print(f"  Versão ID {v.id}:")
        slots = db.query(Grade).filter(Grade.grade_versao_id == v.id).all()
        for s in slots:
            disc = db.query(Disciplina).filter(Disciplina.id == s.disciplina_id).first()
            disc_name = disc.nome if disc else "N/A"
            print(f"    - Slot ID: {s.id} | Dia: {s.dia_semana} | {s.horario_inicio} às {s.horario_fim} | Disciplina: {disc_name} | Estúdio: {s.estudio_id} | Canal: {s.canal_iptv_id} | Tipo: {s.tipo_slot}")
else:
    print("Turma 'teste ok' não encontrada.")

db.close()
