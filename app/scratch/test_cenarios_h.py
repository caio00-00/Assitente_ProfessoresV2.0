import os
import sys
from datetime import date, time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.api.rotas_report import _resolver_horario, _verificar_choque_horario
from app.core.database import SessionLocal
from app.models.class_report import ClassReport
from fastapi import HTTPException

print("=== TESTANDO RESOLUÇÃO DE HORÁRIO ===")
testes_horario = [
    ("A", "1º Horário", "EM 1 TI", "Integral", "07:30 - 08:30"),
    ("B", "1º Horário", "EM 3 MANHÃ", "Manhã", "07:00 - 08:00"),
    ("C", "3º Horário", "EM 1 NOITE", "Manhã", "09:00 - 10:00"),
    ("D", "3º Horário", "EM 1 NOITE", "Noite", "20:00 - 20:45"),
    ("E", "3º Horário", "EJA V", "Noite", "20:00 - 21:00"),
    ("F", "5º Horário", "EJATEC TEC ADM MOD5", "Noite", "None - None")
]

for t in testes_horario:
    st, et = _resolver_horario(t[1], t[2], t[3])
    st_str = st.strftime("%H:%M") if st else "None"
    et_str = et.strftime("%H:%M") if et else "None"
    print(f"Cenário {t[0]}: {t[2]} ({t[3]} - {t[1]}) -> Resolvido: {st_str} - {et_str} | Esperado: {t[4]}")


print("\n=== TESTANDO CHOQUES ===")
db = SessionLocal()
hoje = date(2026, 1, 1)

try:
    # Cenário G
    # A: Estúdio 01, PI 1, Manhã, 1º
    st_a, et_a = _resolver_horario("1º Horário", "EM 3 MANHÃ", "Manhã")
    aula_g1 = ClassReport(
        id="00000000-0000-0000-0000-00000000000g",
        turma_id="00000000-0000-0000-0000-000000000000", disciplina_id="00000000-0000-0000-0000-000000000000", created_by="00000000-0000-0000-0000-000000000000",
        data_aula=hoje, horario_aula="1º Horário", estudio="Estúdio 01", canal_utilizado="Canal PI 1", turno="Manhã", tipo_aula="Normal",
        status="FINALIZADO", is_deleted=False, start_time=st_a, end_time=et_a
    )
    db.add(aula_g1)
    db.flush()
    try:
        _verificar_choque_horario(db, hoje, "Estúdio 01", st_a, et_a, canal_utilizado="Canal PI 1", is_gravacao=False)
        print("Cenário G FALHOU: não bloqueou.")
    except HTTPException as e:
        print(f"Cenário G: BLOQUEADO (correto) -> {e.detail}")

    # Cenário H
    # A: Estúdio 01, PI 1, TI 3º (09:50-10:50) -> Salvo
    st_h1, et_h1 = _resolver_horario("3º Horário", "EM 1 TI", "Integral")
    aula_h1 = ClassReport(
        id="00000000-0000-0000-0000-0000000000h1",
        turma_id="00000000-0000-0000-0000-000000000000", disciplina_id="00000000-0000-0000-0000-000000000000", created_by="00000000-0000-0000-0000-000000000000",
        data_aula=hoje, horario_aula="3º Horário", estudio="Estúdio 02", canal_utilizado="Canal PI 1", turno="Integral", tipo_aula="Normal",
        status="FINALIZADO", is_deleted=False, start_time=st_h1, end_time=et_h1
    )
    db.add(aula_h1)
    db.flush()
    
    # B: Estúdio 02, PI 1, Manhã 3º (09:00-10:00) -> Tento adicionar
    st_h2, et_h2 = _resolver_horario("3º Horário", "EM 3 MANHÃ", "Manhã")
    try:
        _verificar_choque_horario(db, hoje, "Estúdio 02", st_h2, et_h2, canal_utilizado="Canal PI 1", is_gravacao=False)
        print("Cenário H FALHOU: não bloqueou.")
    except HTTPException as e:
        print(f"Cenário H: BLOQUEADO (correto) -> {e.detail}")

    # Cenário I
    aula_i1 = ClassReport(
        id="00000000-0000-0000-0000-0000000000i1",
        turma_id="00000000-0000-0000-0000-000000000000", disciplina_id="00000000-0000-0000-0000-000000000000", created_by="00000000-0000-0000-0000-000000000000",
        data_aula=hoje, horario_aula="", estudio="Estúdio 03", canal_utilizado="Canal PI 3", turno="Manhã", tipo_aula="Gravação",
        status="FINALIZADO", is_deleted=False, start_time=None, end_time=None
    )
    db.add(aula_i1)
    db.flush()
    try:
        _verificar_choque_horario(db, hoje, "Estúdio 03", None, None, canal_utilizado="Canal PI 3", is_gravacao=True)
        print("Cenário I FALHOU: não bloqueou.")
    except HTTPException as e:
        print(f"Cenário I: BLOQUEADO (correto) -> {e.detail}")

    # Cenário J
    try:
        _verificar_choque_horario(db, hoje, "Estúdio 04", st_a, et_a, canal_utilizado="Canal PI 4", is_gravacao=False)
        print("Cenário J: PERMITIDO (correto)")
    except HTTPException as e:
        print(f"Cenário J FALHOU: bloqueou indevidamente -> {e.detail}")

except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    db.rollback()
    db.close()
