import requests
import json

# 1. Login to get token
login_url = "http://localhost:8000/api/v1/auth/login"
data = {"username": "admin@canaleducacao.com", "password": "admin123"}
r_login = requests.post(login_url, data=data)
if r_login.status_code != 200:
    print(f"Login falhou: {r_login.text}")
    exit(1)

token = r_login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. Test audit-stats endpoint
audit_url = "http://localhost:8000/api/v1/reports/audit-stats"
params = {
    "data_inicio": "2026-06-08",
    "data_fim": "2026-06-12"
}

r_audit = requests.get(audit_url, headers=headers, params=params)
print(f"Status HTTP: {r_audit.status_code}")
try:
    res = r_audit.json()
    print("Contagens:")
    print(f"  Previstos da Grade (Pendentes): {res.get('previstos_pendentes')}")
    print(f"  Encontrados OK: {res.get('encontrados_ok')}")
    print(f"  Extras (Fora da Grade): {res.get('extras')}")
    print(f"  Total Grade: {res.get('total_grades')}")
    print(f"  Total Relatórios: {res.get('total_relatorios')}")
    
    print("\nDetalhes das Aulas Pendentes (Primeiras 5):")
    pendentes = res.get("pendentes_detalhes", [])
    for p in pendentes[:5]:
        print(f"  - {p['data']} ({p['dia_semana']}) - {p['horario']} | {p['disciplina_nome']} ({p['professor_nome']}) | Turma: {p['turma_nome']}")
    if len(pendentes) > 5:
        print(f"  ... e mais {len(pendentes) - 5} pendências.")
except Exception as e:
    print(r_audit.text)
