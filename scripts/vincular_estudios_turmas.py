import sys
import os
sys.path.insert(0, "/app")

from app.core.database import SessionLocal
from app.models.turma import Turma
from app.models.auxiliares import Grade
from app.models.infraestrutura import Estudio
from app.models.agenda_estudio import AgendamentoEstudio

def vincular_estudios():
    db = SessionLocal()
    print("--- Iniciando vinculação de Estúdios às Turmas ---")

    # Mapeamento Turma -> Estúdio ID
    # 1: ESTUDIO 01, 2: ESTUDIO 02, 3: ESTUDIO 03, 4: ESTUDIO 04,
    # 5: ESTUDIO 05, 6: ESTUDIO 06, 7: ESTUDIO 07, 8: ESTUDIO 08
    mapeamento = {
        "EM 1 TI": 1,
        "TEC 1": 1,
        "EM 1 NOITE": 1,

        "EM 2 TI": 2,
        "EM 2 NOITE": 2,

        "EM 3 TI": 3,
        "EM 3 NOITE": 3,

        "EM 3 MANHÃ": 4,
        "EM 3 TARDE": 4,
        "EJA ETAPA V": 4,

        "EJATEC TEC ADM MOD1": 5,
        "EJATEC TEC ADM MOD3": 6,
        "EJATEC TEC ADM MOD5": 7,

        "teste ok": 8,
        "TESTE 01": 8,
    }

    total_atualizados = 0

    for nome_turma, estudio_id in mapeamento.items():
        turmas = db.query(Turma).filter(Turma.nomenclatura_padrao.ilike(f"%{nome_turma}%")).all()
        for t in turmas:
            qtd = db.query(Grade).filter(Grade.turma_id == t.id).update(
                {Grade.estudio_id: estudio_id},
                synchronize_session=False
            )
            print(f"Turma '{t.nomenclatura_padrao}' vinculada ao Estúdio {estudio_id:02d} ({qtd} aulas atualizadas)")
            total_atualizados += qtd

    # Limpar os agendamentos manuais de teste para que as aulas regulares da grade fiquem livres e sem choques
    qtd_ag = db.query(AgendamentoEstudio).delete()
    print(f"Limpando {qtd_ag} agendamentos de teste anteriores para exibir a grade limpa.")

    db.commit()
    print(f"\n✅ Concluído! Total de {total_atualizados} aulas da grade vinculadas aos seus estúdios.")
    db.close()

if __name__ == "__main__":
    vincular_estudios()
