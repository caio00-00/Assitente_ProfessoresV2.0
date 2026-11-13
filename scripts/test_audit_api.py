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
    "data_inicio": "2026-05-01",
    "data_fim": "2026-05-09"
}

r_audit = requests.get(audit_url, headers=headers, params=params)
print(f"Status HTTP: {r_audit.status_code}")
try:
    print(json.dumps(r_audit.json(), indent=2))
except Exception as e:
    print(r_audit.text)
