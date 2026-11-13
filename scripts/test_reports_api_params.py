import requests

login_url = "http://localhost:8000/api/v1/auth/login"
data = {"username": "admin@canaleducacao.com", "password": "admin123"}
r_login = requests.post(login_url, data=data)
token = r_login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

url = "http://localhost:8000/api/v1/reports/"
params = {
    "limit": 50, 
    "offset": 0, 
    "sort_by": "data_aula", 
    "sort_order": "desc",
    "data_inicio": "2026-05-01",
    "data_fim": "2026-05-09"
}

r = requests.get(url, headers=headers, params=params)
print(f"Status HTTP: {r.status_code}")
if r.status_code != 200:
    print(r.text)
else:
    print("Sucesso!")
