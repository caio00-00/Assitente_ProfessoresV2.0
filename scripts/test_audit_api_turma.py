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

# 2. Test audit-stats endpoint without turma_id
audit_url = "http://localhost:8000/api/v1/reports/audit-stats"
params_geral = {
    "data_inicio": "2026-05-01",
    "data_fim": "2026-05-09"
}

r_geral = requests.get(audit_url, headers=headers, params=params_geral)
print(f"--- SEM TURMA SELECIONADA ---")
print(json.dumps(r_geral.json(), indent=2))

# 3. Test audit-stats endpoint with turma_id=1
params_turma = {
    "data_inicio": "2026-05-01",
    "data_fim": "2026-05-09",
    "turma_id": "8d44ddf6-b38f-4a4d-bccb-bb8abcc9019c" # Valid UUID from previous logs
}

r_turma = requests.get(audit_url, headers=headers, params=params_turma)
print(f"\n--- COM TURMA SELECIONADA ---")
try:
    print(json.dumps(r_turma.json(), indent=2))
except Exception:
    print(r_turma.text)
