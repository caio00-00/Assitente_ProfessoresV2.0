import requests

# 1. Login to get token
login_url = "http://localhost:8000/api/v1/auth/login"
data = {"username": "admin@canaleducacao.com", "password": "admin123"}
r_login = requests.post(login_url, data=data)
token = r_login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. Test /api/v1/reports/ endpoint
url = "http://localhost:8000/api/v1/reports/"
params = {"limit": 50, "offset": 0}

r = requests.get(url, headers=headers, params=params)
print(f"Status HTTP: {r.status_code}")
print(r.text[:500])
