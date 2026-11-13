import os
import sys

# Adjust path so we can import from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.api.rotas_report import _resolver_horario

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
