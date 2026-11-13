import os
import sys
from datetime import date, time, datetime

# Adjust path so we can import from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.api.rotas_report import _resolver_horario, _verificar_choque_horario
from app.core.database import SessionLocal
from app.models.class_report import ClassReport
from fastapi import HTTPException

print("=== TESTANDO CENÁRIOS A, B e C ===")

# CENÁRIO A
# Turma: EM 1 NOITE, Turno selecionado: Manhã, Horário: 3º Horário
st_a, et_a = _resolver_horario("3º Horário", "EM 1 NOITE", turno_usuario="Manhã")
print(f"CENÁRIO A - Esperado: 09:00-10:00 | Resolvido: {st_a.strftime('%H:%M')} às {et_a.strftime('%H:%M') if et_a else None}")

# CENÁRIO B
# Turma: EM 1 NOITE, Turno: Noite, Horário: 3º Horário
st_b, et_b = _resolver_horario("3º Horário", "EM 1 NOITE", turno_usuario="Noite")
print(f"CENÁRIO B - Esperado: 20:00-20:45 | Resolvido: {st_b.strftime('%H:%M')} às {et_b.strftime('%H:%M') if et_b else None}")

# CENÁRIO C
# Turma: EJATEC TEC ADM MOD1, Turno: Manhã, Horário: 1º Horário
st_c, et_c = _resolver_horario("1º Horário", "EJATEC TEC ADM MOD1", turno_usuario="Manhã")
print(f"CENÁRIO C - Esperado: 07:00-08:00 | Resolvido: {st_c.strftime('%H:%M')} às {et_c.strftime('%H:%M') if et_c else None}")

print("\n=== TESTANDO CENÁRIO D ===")
db = SessionLocal()
try:
    hoje = date.today()
    
    # Aula A: Estúdio 01, Canal PI 3, Manhã, 1º Horário (07:00-08:00)
    aula_a = ClassReport(
        turma_id="00000000-0000-0000-0000-000000000000",
        disciplina_id="00000000-0000-0000-0000-000000000000",
        created_by="00000000-0000-0000-0000-000000000000",
        data_aula=hoje,
        horario_aula="1º Horário",
        estudio="Estúdio 01",
        canal_utilizado="Canal PI 3",
        turno="Manhã",
        tipo_aula="Normal",
        conteudo_ministrado="Teste",
        interacao_professor_aluno="Não",
        problema_material="Não",
        teve_substituicao=False,
        teve_atraso=False,
        status="RASCUNHO",
        regular="Sim",
        start_time=time(7, 0),
        end_time=time(8, 0),
        is_deleted=False,
        youtube_link="link",
        bncc_habilidades="Nenhuma"
    )
    db.add(aula_a)
    db.flush() # Grava no BD sem comitar para testarmos
    
    # Aula B: Estúdio 03, Canal PI 3, Manhã, 1º Horário (07:00-08:00)
    print("Tentando criar Aula B e verificando choque...")
    try:
        _verificar_choque_horario(
            db=db,
            data_aula=hoje,
            estudio="Estúdio 03",
            start=time(7, 0),
            end=time(8, 0),
            canal_utilizado="Canal PI 3"
        )
        print("CENÁRIO D - FALHOU: Não levantou exceção de conflito!")
    except HTTPException as e:
        print(f"CENÁRIO D - SUCESSO: Levantou exceção corretamente -> {e.detail}")

finally:
    db.rollback() # Limpa as alterações
    db.close()
