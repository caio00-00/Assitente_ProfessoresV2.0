import os
import sys
from datetime import date, time

# Adjust path so we can import from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.api.rotas_report import _resolver_horario, _verificar_choque_horario
from app.core.database import SessionLocal
from app.models.class_report import ClassReport
from fastapi import HTTPException

print("=== TESTANDO HORÁRIOS ===")

# A: EM 3 TI 1, Manhã, 1º Horário -> Esperado 07:30-08:30
st, et = _resolver_horario("1º Horário", "EM 3 TI 1", "Manhã")
print(f"Cenário A: {st} - {et}")

# B: EM 3 MANHÃ, Manhã, 1º Horário -> Esperado 07:00-08:00
st, et = _resolver_horario("1º Horário", "EM 3 MANHÃ", "Manhã")
print(f"Cenário B: {st} - {et}")

# C: EM 1 NOITE, Manhã, 3º Horário -> Esperado 09:00-10:00
st, et = _resolver_horario("3º Horário", "EM 1 NOITE", "Manhã")
print(f"Cenário C: {st} - {et}")

# D: EM 1 NOITE, Noite, 3º Horário -> Esperado 20:00-20:45
st, et = _resolver_horario("3º Horário", "EM 1 NOITE", "Noite")
print(f"Cenário D: {st} - {et}")

# E: EJATEC MOD1, Noite, 3º Horário -> Esperado 20:00-21:00
st, et = _resolver_horario("3º Horário", "EJATEC MOD1", "Noite")
print(f"Cenário E: {st} - {et}")

print("\n=== TESTANDO CHOQUE ===")
db = SessionLocal()
hoje = date(2026, 1, 1)

try:
    # Cenário F
    # Aula A: Estúdio 01, Canal PI 3, Manhã, 1º Horário
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
        status="FINALIZADO",
        is_deleted=False
    )
    db.add(aula_a)
    # Ignorando erro de FK usando autoflush=False ou apenas instanciando o objeto e testando se fosse possível, 
    # but the simplest is just commit or flush with disabled constraints. 
    # Actually wait, let's just create a mock or disable foreign keys.
except Exception as e:
    print(e)
finally:
    db.close()
