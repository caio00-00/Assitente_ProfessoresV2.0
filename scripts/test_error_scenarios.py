"""
Canal Educação v3.0 — Teste Exaustivo de Cenários de Erro
Executa requisições contra todos os endpoints e registra inconsistências.
"""

import sys
import os
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
import requests
from jose import jwt

BASE = "http://localhost:8000"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASS = "admin123"

# ── Configurações JWT para forjar tokens ────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "troque-pela-sua-chave")
ALGORITHM = "HS256"

results = []

def log_result(endpoint, method, scenario, status_code, body, expected_status=None, notes=""):
    detail = ""
    if isinstance(body, dict):
        detail = body.get("detail", str(body))
    elif isinstance(body, list):
        detail = str(body)[:200]
    else:
        detail = str(body)[:200]
    
    # Verificação semântica
    semantic_ok = True
    semantic_note = notes
    if expected_status and status_code != expected_status:
        semantic_ok = False
        semantic_note += f" ESPERADO {expected_status}, RECEBIDO {status_code}."
    
    results.append({
        "endpoint": f"{method} {endpoint}",
        "scenario": scenario,
        "status": status_code,
        "detail": detail,
        "expected": expected_status,
        "semantic_ok": semantic_ok,
        "notes": semantic_note,
    })
    
    icon = "✅" if semantic_ok else "❌"
    print(f"  {icon} [{status_code}] {scenario}: {str(detail)[:80]}")


def get_admin_token():
    """Obtém token JWT do admin"""
    r = requests.post(f"{BASE}/api/v1/auth/login", data={
        "username": ADMIN_EMAIL,
        "password": ADMIN_PASS,
    })
    if r.status_code == 200:
        return r.json()["access_token"]
    print(f"⚠️ Falha ao obter token admin: {r.status_code} {r.text}")
    return None


def make_expired_token():
    """Cria um JWT expirado"""
    payload = {
        "sub": ADMIN_EMAIL,
        "role": "admin",
        "user_id": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def make_invalid_token():
    """Cria um JWT com assinatura inválida"""
    payload = {
        "sub": ADMIN_EMAIL,
        "role": "admin",
        "user_id": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, "wrong_secret_key", algorithm=ALGORITHM)


def make_token_for_role(role, email=None):
    """Cria um JWT válido para um role específico"""
    payload = {
        "sub": email or f"test_{role}@test.com",
        "role": role,
        "user_id": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════
# TESTES
# ═══════════════════════════════════════════════════════════════════════


def test_login():
    """Testa cenários de erro do POST /api/v1/auth/login"""
    print("\n" + "="*70)
    print("📌 POST /api/v1/auth/login")
    print("="*70)
    
    # 1. Email inexistente
    r = requests.post(f"{BASE}/api/v1/auth/login", data={
        "username": "naoexiste@email.com",
        "password": "qualquer123",
    })
    log_result("/api/v1/auth/login", "POST", "Email inexistente", r.status_code, r.json(), 401)
    
    # 2. Senha errada
    r = requests.post(f"{BASE}/api/v1/auth/login", data={
        "username": ADMIN_EMAIL,
        "password": "senhaerrada",
    })
    log_result("/api/v1/auth/login", "POST", "Senha errada", r.status_code, r.json(), 401)
    
    # 3. Campo username vazio
    r = requests.post(f"{BASE}/api/v1/auth/login", data={
        "username": "",
        "password": "admin123",
    })
    log_result("/api/v1/auth/login", "POST", "Username vazio", r.status_code, r.json())
    
    # 4. Sem campo password
    r = requests.post(f"{BASE}/api/v1/auth/login", data={
        "username": ADMIN_EMAIL,
    })
    log_result("/api/v1/auth/login", "POST", "Sem campo password", r.status_code, r.json(), 422)
    
    # 5. Body vazio (sem form data)
    r = requests.post(f"{BASE}/api/v1/auth/login")
    log_result("/api/v1/auth/login", "POST", "Body vazio (sem form data)", r.status_code, r.json(), 422)
    
    # 6. Content-Type JSON em vez de form
    r = requests.post(f"{BASE}/api/v1/auth/login", json={
        "username": ADMIN_EMAIL,
        "password": ADMIN_PASS,
    })
    log_result("/api/v1/auth/login", "POST", "JSON body em vez de form-data", r.status_code, r.json(), 422)


def test_me(admin_token):
    """Testa cenários de erro do GET /api/v1/auth/me"""
    print("\n" + "="*70)
    print("📌 GET /api/v1/auth/me")
    print("="*70)
    
    # 1. Sem token
    r = requests.get(f"{BASE}/api/v1/auth/me")
    log_result("/api/v1/auth/me", "GET", "Sem token de autenticação", r.status_code, r.json(), 401)
    
    # 2. Token expirado
    expired = make_expired_token()
    r = requests.get(f"{BASE}/api/v1/auth/me", headers=auth_header(expired))
    log_result("/api/v1/auth/me", "GET", "Token JWT expirado", r.status_code, r.json(), 401)
    
    # 3. Token com assinatura inválida
    invalid = make_invalid_token()
    r = requests.get(f"{BASE}/api/v1/auth/me", headers=auth_header(invalid))
    log_result("/api/v1/auth/me", "GET", "Token com assinatura inválida", r.status_code, r.json(), 401)
    
    # 4. Token com string aleatória
    r = requests.get(f"{BASE}/api/v1/auth/me", headers=auth_header("abc.def.ghi"))
    log_result("/api/v1/auth/me", "GET", "Token string aleatória", r.status_code, r.json(), 401)
    
    # 5. Token de usuário inexistente (email não existe no DB)
    fake_user_token = make_token_for_role("admin", "usuario_fake_inexistente@test.com")
    r = requests.get(f"{BASE}/api/v1/auth/me", headers=auth_header(fake_user_token))
    log_result("/api/v1/auth/me", "GET", "Token de usuário inexistente no DB", r.status_code, r.json(), 401)


def test_me_theme(admin_token):
    """Testa cenários de erro do PATCH /api/v1/auth/me/theme"""
    print("\n" + "="*70)
    print("📌 PATCH /api/v1/auth/me/theme")
    print("="*70)
    
    # 1. Sem token
    r = requests.patch(f"{BASE}/api/v1/auth/me/theme", json={"theme_preference": "light"})
    log_result("/api/v1/auth/me/theme", "PATCH", "Sem token", r.status_code, r.json(), 401)
    
    # 2. Body vazio
    r = requests.patch(f"{BASE}/api/v1/auth/me/theme", headers=auth_header(admin_token), json={})
    log_result("/api/v1/auth/me/theme", "PATCH", "Body vazio (sem theme_preference)", r.status_code, r.json(), 422)
    
    # 3. Campo com tipo errado
    r = requests.patch(f"{BASE}/api/v1/auth/me/theme", headers=auth_header(admin_token), json={"theme_preference": 12345})
    log_result("/api/v1/auth/me/theme", "PATCH", "theme_preference com tipo int", r.status_code, r.json())


def test_invite(admin_token):
    """Testa cenários de erro do POST /api/v1/auth/invite"""
    print("\n" + "="*70)
    print("📌 POST /api/v1/auth/invite")
    print("="*70)
    
    # 1. Sem token
    r = requests.post(f"{BASE}/api/v1/auth/invite", json={
        "email": "novo@test.com", "full_name": "Teste", "role": "assistente"
    })
    log_result("/api/v1/auth/invite", "POST", "Sem token", r.status_code, r.json(), 401)
    
    # 2. Role insuficiente (assistente tentando convidar)
    assistente_token = make_token_for_role("assistente", ADMIN_EMAIL)
    r = requests.post(f"{BASE}/api/v1/auth/invite", json={
        "email": "novo@test.com", "full_name": "Teste", "role": "assistente"
    }, headers=auth_header(assistente_token))
    log_result("/api/v1/auth/invite", "POST", "Assistente tentando convidar", r.status_code, r.json(), 403)
    
    # 3. Email duplicado (email do admin)
    r = requests.post(f"{BASE}/api/v1/auth/invite", json={
        "email": ADMIN_EMAIL, "full_name": "Teste Dup", "role": "assistente"
    }, headers=auth_header(admin_token))
    log_result("/api/v1/auth/invite", "POST", "Email duplicado (admin existente)", r.status_code, r.json(), 409)
    
    # 4. Email inválido
    r = requests.post(f"{BASE}/api/v1/auth/invite", json={
        "email": "nao-e-email", "full_name": "Teste", "role": "assistente"
    }, headers=auth_header(admin_token))
    log_result("/api/v1/auth/invite", "POST", "Email inválido (formato)", r.status_code, r.json(), 422)
    
    # 5. Campos obrigatórios ausentes
    r = requests.post(f"{BASE}/api/v1/auth/invite", json={}, headers=auth_header(admin_token))
    log_result("/api/v1/auth/invite", "POST", "Campos obrigatórios ausentes", r.status_code, r.json(), 422)
    
    # 6. Gestor tentando criar admin
    gestor_token = make_token_for_role("gestor", ADMIN_EMAIL)
    r = requests.post(f"{BASE}/api/v1/auth/invite", json={
        "email": "novoadmin@test.com", "full_name": "Novo Admin", "role": "admin"
    }, headers=auth_header(gestor_token))
    log_result("/api/v1/auth/invite", "POST", "Gestor tentando criar admin", r.status_code, r.json(), 403)


def test_confirm():
    """Testa cenários de erro do POST /api/v1/auth/confirm"""
    print("\n" + "="*70)
    print("📌 POST /api/v1/auth/confirm")
    print("="*70)
    
    # 1. Token de convite inexistente
    r = requests.post(f"{BASE}/api/v1/auth/confirm", json={
        "token": str(uuid.uuid4()),
        "password": "senhanova123"
    })
    log_result("/api/v1/auth/confirm", "POST", "Token de convite inexistente", r.status_code, r.json(), 404)
    
    # 2. Sem campos obrigatórios
    r = requests.post(f"{BASE}/api/v1/auth/confirm", json={})
    log_result("/api/v1/auth/confirm", "POST", "Campos obrigatórios ausentes", r.status_code, r.json(), 422)
    
    # 3. Senha muito curta
    r = requests.post(f"{BASE}/api/v1/auth/confirm", json={
        "token": str(uuid.uuid4()),
        "password": "12345"  # min_length=6
    })
    log_result("/api/v1/auth/confirm", "POST", "Senha curta (< 6 chars)", r.status_code, r.json(), 422)
    
    # 4. Token vazio
    r = requests.post(f"{BASE}/api/v1/auth/confirm", json={
        "token": "",
        "password": "senhanova123"
    })
    log_result("/api/v1/auth/confirm", "POST", "Token vazio", r.status_code, r.json(), 404,
               notes="Token vazio deveria retornar 400 ou 422, não 404")


def test_forgot_password():
    """Testa cenários de erro do POST /api/v1/auth/forgot-password"""
    print("\n" + "="*70)
    print("📌 POST /api/v1/auth/forgot-password")
    print("="*70)
    
    # 1. Email inexistente (deve retornar 200 por segurança)
    r = requests.post(f"{BASE}/api/v1/auth/forgot-password", json={
        "email": "naoexiste@mail.com"
    })
    log_result("/api/v1/auth/forgot-password", "POST", "Email inexistente (retorna 200 por segurança)", 
               r.status_code, r.json(), 200)
    
    # 2. Email inválido
    r = requests.post(f"{BASE}/api/v1/auth/forgot-password", json={
        "email": "nao-e-email"
    })
    log_result("/api/v1/auth/forgot-password", "POST", "Email com formato inválido", r.status_code, r.json(), 422)
    
    # 3. Sem email
    r = requests.post(f"{BASE}/api/v1/auth/forgot-password", json={})
    log_result("/api/v1/auth/forgot-password", "POST", "Sem campo email", r.status_code, r.json(), 422)


def test_reset_password():
    """Testa cenários de erro do POST /api/v1/auth/reset-password"""
    print("\n" + "="*70)
    print("📌 POST /api/v1/auth/reset-password")
    print("="*70)
    
    # 1. Token de reset inexistente
    r = requests.post(f"{BASE}/api/v1/auth/reset-password", json={
        "token": str(uuid.uuid4()),
        "password": "novasenha123"
    })
    log_result("/api/v1/auth/reset-password", "POST", "Token de reset inexistente", r.status_code, r.json(), 400)
    
    # 2. Sem campos
    r = requests.post(f"{BASE}/api/v1/auth/reset-password", json={})
    log_result("/api/v1/auth/reset-password", "POST", "Campos obrigatórios ausentes", r.status_code, r.json(), 422)
    
    # 3. Senha curta
    r = requests.post(f"{BASE}/api/v1/auth/reset-password", json={
        "token": str(uuid.uuid4()),
        "password": "123"
    })
    log_result("/api/v1/auth/reset-password", "POST", "Senha curta (< 6 chars)", r.status_code, r.json(), 422)


def test_users(admin_token):
    """Testa cenários de erro de gestão de utilizadores"""
    print("\n" + "="*70)
    print("📌 GET /api/v1/auth/users")
    print("="*70)
    
    # 1. Sem token
    r = requests.get(f"{BASE}/api/v1/auth/users")
    log_result("/api/v1/auth/users", "GET", "Sem token", r.status_code, r.json(), 401)
    
    # 2. Role insuficiente (assistente)
    assistente_token = make_token_for_role("assistente", ADMIN_EMAIL)
    r = requests.get(f"{BASE}/api/v1/auth/users", headers=auth_header(assistente_token))
    log_result("/api/v1/auth/users", "GET", "Assistente tentando listar users", r.status_code, r.json(), 403)
    
    # 3. Token expirado
    expired = make_expired_token()
    r = requests.get(f"{BASE}/api/v1/auth/users", headers=auth_header(expired))
    log_result("/api/v1/auth/users", "GET", "Token expirado", r.status_code, r.json(), 401)
    
    fake_id = str(uuid.uuid4())
    
    # ── Deactivate ──
    print("\n📌 PATCH /api/v1/auth/users/{id}/deactivate")
    
    # 4. User inexistente
    r = requests.patch(f"{BASE}/api/v1/auth/users/{fake_id}/deactivate", headers=auth_header(admin_token))
    log_result(f"/api/v1/auth/users/{{id}}/deactivate", "PATCH", "User inexistente", r.status_code, r.json(), 404)
    
    # 5. Sem token
    r = requests.patch(f"{BASE}/api/v1/auth/users/{fake_id}/deactivate")
    log_result(f"/api/v1/auth/users/{{id}}/deactivate", "PATCH", "Sem token", r.status_code, r.json(), 401)
    
    # 6. Role insuficiente (gestor)
    gestor_token = make_token_for_role("gestor", ADMIN_EMAIL)
    r = requests.patch(f"{BASE}/api/v1/auth/users/{fake_id}/deactivate", headers=auth_header(gestor_token))
    log_result(f"/api/v1/auth/users/{{id}}/deactivate", "PATCH", "Gestor tentando desativar", r.status_code, r.json(), 403)
    
    # 7. Admin tentando desativar a si próprio — precisa do ID real
    r = requests.get(f"{BASE}/api/v1/auth/me", headers=auth_header(admin_token))
    if r.status_code == 200:
        admin_id = r.json()["id"]
        r2 = requests.patch(f"{BASE}/api/v1/auth/users/{admin_id}/deactivate", headers=auth_header(admin_token))
        log_result(f"/api/v1/auth/users/{{id}}/deactivate", "PATCH", "Admin desativando a si próprio", r2.status_code, r2.json(), 400)
    
    # ── Activate ──
    print("\n📌 PATCH /api/v1/auth/users/{id}/activate")
    
    r = requests.patch(f"{BASE}/api/v1/auth/users/{fake_id}/activate", headers=auth_header(admin_token))
    log_result(f"/api/v1/auth/users/{{id}}/activate", "PATCH", "User inexistente", r.status_code, r.json(), 404)
    
    # User já ativo
    r = requests.get(f"{BASE}/api/v1/auth/me", headers=auth_header(admin_token))
    if r.status_code == 200:
        admin_id = r.json()["id"]
        r2 = requests.patch(f"{BASE}/api/v1/auth/users/{admin_id}/activate", headers=auth_header(admin_token))
        log_result(f"/api/v1/auth/users/{{id}}/activate", "PATCH", "User já está ativo", r2.status_code, r2.json(), 400)
    
    # ── Change Role ──
    print("\n📌 PATCH /api/v1/auth/users/{id}/role")
    
    # Role inválido
    r = requests.patch(f"{BASE}/api/v1/auth/users/{fake_id}/role?role=superuser", headers=auth_header(admin_token))
    log_result(f"/api/v1/auth/users/{{id}}/role", "PATCH", "Role inválido (superuser)", r.status_code, r.json(), 400)
    
    # User inexistente
    r = requests.patch(f"{BASE}/api/v1/auth/users/{fake_id}/role?role=gestor", headers=auth_header(admin_token))
    log_result(f"/api/v1/auth/users/{{id}}/role", "PATCH", "User inexistente", r.status_code, r.json(), 404)
    
    # Sem parâmetro role
    r = requests.patch(f"{BASE}/api/v1/auth/users/{fake_id}/role", headers=auth_header(admin_token))
    log_result(f"/api/v1/auth/users/{{id}}/role", "PATCH", "Sem parâmetro role", r.status_code, r.json(), 422)
    
    # Gestor tentando mudar role
    r = requests.patch(f"{BASE}/api/v1/auth/users/{fake_id}/role?role=admin", headers=auth_header(gestor_token))
    log_result(f"/api/v1/auth/users/{{id}}/role", "PATCH", "Gestor tentando mudar role", r.status_code, r.json(), 403)


def test_force_reset(admin_token):
    """Testa cenários de erro do POST /api/v1/auth/users/{id}/force-reset"""
    print("\n" + "="*70)
    print("📌 POST /api/v1/auth/users/{id}/force-reset")
    print("="*70)
    
    fake_id = str(uuid.uuid4())
    
    # 1. User inexistente
    r = requests.post(f"{BASE}/api/v1/auth/users/{fake_id}/force-reset", headers=auth_header(admin_token))
    log_result(f"/api/v1/auth/users/{{id}}/force-reset", "POST", "User inexistente", r.status_code, r.json(), 404)
    
    # 2. ID inválido (não UUID)
    r = requests.post(f"{BASE}/api/v1/auth/users/nao-e-uuid/force-reset", headers=auth_header(admin_token))
    log_result(f"/api/v1/auth/users/{{id}}/force-reset", "POST", "ID não é UUID válido", r.status_code, r.json(), 400)
    
    # 3. Sem token
    r = requests.post(f"{BASE}/api/v1/auth/users/{fake_id}/force-reset")
    log_result(f"/api/v1/auth/users/{{id}}/force-reset", "POST", "Sem token", r.status_code, r.json(), 401)
    
    # 4. Gestor tentando
    gestor_token = make_token_for_role("gestor", ADMIN_EMAIL)
    r = requests.post(f"{BASE}/api/v1/auth/users/{fake_id}/force-reset", headers=auth_header(gestor_token))
    log_result(f"/api/v1/auth/users/{{id}}/force-reset", "POST", "Gestor tentando force-reset", r.status_code, r.json(), 403)


def test_audit_logs(admin_token):
    """Testa cenários de erro do GET /api/v1/auth/audit-logs"""
    print("\n" + "="*70)
    print("📌 GET /api/v1/auth/audit-logs")
    print("="*70)
    
    # 1. Sem token
    r = requests.get(f"{BASE}/api/v1/auth/audit-logs")
    log_result("/api/v1/auth/audit-logs", "GET", "Sem token", r.status_code, r.json(), 401)
    
    # 2. Assistente tentando
    assistente_token = make_token_for_role("assistente", ADMIN_EMAIL)
    r = requests.get(f"{BASE}/api/v1/auth/audit-logs", headers=auth_header(assistente_token))
    log_result("/api/v1/auth/audit-logs", "GET", "Assistente tentando ver logs", r.status_code, r.json(), 403)
    
    # 3. Gestor tentando
    gestor_token = make_token_for_role("gestor", ADMIN_EMAIL)
    r = requests.get(f"{BASE}/api/v1/auth/audit-logs", headers=auth_header(gestor_token))
    log_result("/api/v1/auth/audit-logs", "GET", "Gestor tentando ver audit-logs", r.status_code, r.json(), 403)
    
    # 4. Parâmetros inválidos
    r = requests.get(f"{BASE}/api/v1/auth/audit-logs?limit=0", headers=auth_header(admin_token))
    log_result("/api/v1/auth/audit-logs", "GET", "limit=0 (abaixo do mínimo)", r.status_code, r.json(), 422)
    
    r = requests.get(f"{BASE}/api/v1/auth/audit-logs?limit=999", headers=auth_header(admin_token))
    log_result("/api/v1/auth/audit-logs", "GET", "limit=999 (acima do máximo)", r.status_code, r.json(), 422)
    
    r = requests.get(f"{BASE}/api/v1/auth/audit-logs?offset=-1", headers=auth_header(admin_token))
    log_result("/api/v1/auth/audit-logs", "GET", "offset=-1 (negativo)", r.status_code, r.json(), 422)


def test_bootstrap(admin_token):
    """Testa cenários de erro do POST /api/v1/auth/bootstrap"""
    print("\n" + "="*70)
    print("📌 POST /api/v1/auth/bootstrap")
    print("="*70)
    
    # 1. Sistema já tem usuários
    r = requests.post(f"{BASE}/api/v1/auth/bootstrap")
    log_result("/api/v1/auth/bootstrap", "POST", "Sistema já tem usuários", r.status_code, r.json(), 403)


def test_cadastros(admin_token):
    """Testa cenários de erro de cadastros (professores, disciplinas, diretores)"""
    print("\n" + "="*70)
    print("📌 CADASTROS — Professores, Disciplinas, Diretores")
    print("="*70)
    
    fake_id = str(uuid.uuid4())
    
    # ── Professores ──
    print("\n  📎 GET /api/v1/cadastros/professores")
    
    r = requests.get(f"{BASE}/api/v1/cadastros/professores")
    log_result("/api/v1/cadastros/professores", "GET", "Sem token", r.status_code, r.json(), 401)
    
    print("\n  📎 POST /api/v1/cadastros/professores")
    
    # Sem token
    r = requests.post(f"{BASE}/api/v1/cadastros/professores", json={"nome": "Teste"})
    log_result("/api/v1/cadastros/professores", "POST", "Sem token", r.status_code, r.json(), 401)
    
    # Body vazio
    r = requests.post(f"{BASE}/api/v1/cadastros/professores", json={}, headers=auth_header(admin_token))
    log_result("/api/v1/cadastros/professores", "POST", "Body vazio", r.status_code, r.json(), 422)
    
    # Role insuficiente
    assistente_token = make_token_for_role("assistente", ADMIN_EMAIL)
    r = requests.post(f"{BASE}/api/v1/cadastros/professores", json={"nome": "Teste"}, headers=auth_header(assistente_token))
    log_result("/api/v1/cadastros/professores", "POST", "Assistente tentando criar", r.status_code, r.json(), 403)
    
    print("\n  📎 PATCH /api/v1/cadastros/professores/{id}")
    
    # Professor inexistente
    r = requests.patch(f"{BASE}/api/v1/cadastros/professores/{fake_id}", json={"nome": "X"}, headers=auth_header(admin_token))
    log_result(f"/api/v1/cadastros/professores/{{id}}", "PATCH", "Professor inexistente", r.status_code, r.json(), 404)
    
    print("\n  📎 PATCH /api/v1/cadastros/professores/{id}/toggle-active")
    
    r = requests.patch(f"{BASE}/api/v1/cadastros/professores/{fake_id}/toggle-active", headers=auth_header(admin_token))
    log_result(f"/api/v1/cadastros/professores/{{id}}/toggle-active", "PATCH", "Professor inexistente", r.status_code, r.json(), 404)
    
    # ── Disciplinas ──
    print("\n  📎 POST /api/v1/cadastros/disciplinas")
    
    r = requests.post(f"{BASE}/api/v1/cadastros/disciplinas", json={}, headers=auth_header(admin_token))
    log_result("/api/v1/cadastros/disciplinas", "POST", "Body vazio", r.status_code, r.json(), 422)
    
    print("\n  📎 PATCH /api/v1/cadastros/disciplinas/{id}")
    
    r = requests.patch(f"{BASE}/api/v1/cadastros/disciplinas/{fake_id}", json={"nome": "X"}, headers=auth_header(admin_token))
    log_result(f"/api/v1/cadastros/disciplinas/{{id}}", "PATCH", "Disciplina inexistente", r.status_code, r.json(), 404)
    
    print("\n  📎 PATCH /api/v1/cadastros/disciplinas/{id}/toggle-active")
    
    r = requests.patch(f"{BASE}/api/v1/cadastros/disciplinas/{fake_id}/toggle-active", headers=auth_header(admin_token))
    log_result(f"/api/v1/cadastros/disciplinas/{{id}}/toggle-active", "PATCH", "Disciplina inexistente", r.status_code, r.json(), 404)
    
    # ── Diretores ──
    print("\n  📎 POST /api/v1/cadastros/diretores")
    
    r = requests.post(f"{BASE}/api/v1/cadastros/diretores", json={}, headers=auth_header(admin_token))
    log_result("/api/v1/cadastros/diretores", "POST", "Body vazio", r.status_code, r.json(), 422)
    
    print("\n  📎 PATCH /api/v1/cadastros/diretores/{id}")
    
    r = requests.patch(f"{BASE}/api/v1/cadastros/diretores/{fake_id}", json={"nome": "X"}, headers=auth_header(admin_token))
    log_result(f"/api/v1/cadastros/diretores/{{id}}", "PATCH", "Diretor inexistente", r.status_code, r.json(), 404)
    
    print("\n  📎 PATCH /api/v1/cadastros/diretores/{id}/toggle-active")
    
    r = requests.patch(f"{BASE}/api/v1/cadastros/diretores/{fake_id}/toggle-active", headers=auth_header(admin_token))
    log_result(f"/api/v1/cadastros/diretores/{{id}}/toggle-active", "PATCH", "Diretor inexistente", r.status_code, r.json(), 404)


def test_turmas(admin_token):
    """Testa cenários de erro de turmas"""
    print("\n" + "="*70)
    print("📌 TURMAS")
    print("="*70)
    
    fake_id = str(uuid.uuid4())
    
    # GET sem token
    r = requests.get(f"{BASE}/api/v1/turmas/")
    log_result("/api/v1/turmas/", "GET", "Sem token", r.status_code, r.json(), 401)
    
    # POST sem token
    r = requests.post(f"{BASE}/api/v1/turmas/", json={})
    log_result("/api/v1/turmas/", "POST", "Sem token", r.status_code, r.json(), 401)
    
    # POST body incompleto
    r = requests.post(f"{BASE}/api/v1/turmas/", json={}, headers=auth_header(admin_token))
    log_result("/api/v1/turmas/", "POST", "Body vazio", r.status_code, r.json(), 422)
    
    # POST turno inválido
    r = requests.post(f"{BASE}/api/v1/turmas/", json={
        "nome": "Teste Turma",
        "modalidade": "Regular",
        "serie_modulo": "1º Ano",
        "turno": "MADRUGADA"
    }, headers=auth_header(admin_token))
    log_result("/api/v1/turmas/", "POST", "Turno inválido (MADRUGADA)", r.status_code, r.json(), 400)
    
    # POST EJA com turno errado
    r = requests.post(f"{BASE}/api/v1/turmas/", json={
        "nome": "EJA Turma V",
        "modalidade": "EJA",
        "serie_modulo": "EJA V",
        "turno": "MANHÃ"
    }, headers=auth_header(admin_token))
    log_result("/api/v1/turmas/", "POST", "EJA com turno MANHÃ (regra negócio)", r.status_code, r.json(), 400)
    
    # GET turma inexistente
    r = requests.get(f"{BASE}/api/v1/turmas/{fake_id}", headers=auth_header(admin_token))
    log_result(f"/api/v1/turmas/{{id}}", "GET", "Turma inexistente", r.status_code, r.json(), 404)
    
    # PUT turma inexistente
    r = requests.put(f"{BASE}/api/v1/turmas/{fake_id}", json={
        "nome": "X", "modalidade": "Y", "serie_modulo": "Z", "turno": "MANHÃ"
    }, headers=auth_header(admin_token))
    log_result(f"/api/v1/turmas/{{id}}", "PUT", "Turma inexistente", r.status_code, r.json(), 404)
    
    # Toggle turma inexistente
    r = requests.patch(f"{BASE}/api/v1/turmas/{fake_id}/toggle-active", headers=auth_header(admin_token))
    log_result(f"/api/v1/turmas/{{id}}/toggle-active", "PATCH", "Turma inexistente", r.status_code, r.json(), 404)
    
    # Grade turma inexistente
    r = requests.get(f"{BASE}/api/v1/turmas/{fake_id}/grade", headers=auth_header(admin_token))
    log_result(f"/api/v1/turmas/{{id}}/grade", "GET", "Turma inexistente", r.status_code, r.json(), 404)
    
    # Grade com data inválida
    # Buscar uma turma real
    r = requests.get(f"{BASE}/api/v1/turmas/", headers=auth_header(admin_token))
    if r.status_code == 200 and len(r.json()) > 0:
        real_turma_id = r.json()[0]["id"]
        r2 = requests.get(f"{BASE}/api/v1/turmas/{real_turma_id}/grade?data_consulta=invalido", headers=auth_header(admin_token))
        log_result(f"/api/v1/turmas/{{id}}/grade", "GET", "Data inválida (formato)", r2.status_code, r2.json(), 400)
    
    # POST grade horário inválido
    r = requests.post(f"{BASE}/api/v1/turmas/{fake_id}/grade", json={
        "disciplina_id": str(uuid.uuid4()),
        "dia_semana": "Segunda",
        "horario_inicio": "invalido",
        "horario_fim": "99:99"
    }, headers=auth_header(admin_token))
    log_result(f"/api/v1/turmas/{{id}}/grade", "POST", "Formato de hora inválido", r.status_code, r.json(), 400)
    
    # DELETE grade inexistente
    r = requests.delete(f"{BASE}/api/v1/turmas/grade/{fake_id}", headers=auth_header(admin_token))
    log_result(f"/api/v1/turmas/grade/{{id}}", "DELETE", "Grade inexistente", r.status_code, r.json(), 404)


def test_reports(admin_token):
    """Testa cenários de erro de relatórios"""
    print("\n" + "="*70)
    print("📌 RELATÓRIOS")
    print("="*70)
    
    fake_id = str(uuid.uuid4())
    
    # GET sem token
    r = requests.get(f"{BASE}/api/v1/reports/")
    log_result("/api/v1/reports/", "GET", "Sem token", r.status_code, r.json(), 401)
    
    # GET relatório inexistente
    r = requests.get(f"{BASE}/api/v1/reports/{fake_id}", headers=auth_header(admin_token))
    log_result(f"/api/v1/reports/{{id}}", "GET", "Relatório inexistente", r.status_code, r.json(), 404)
    
    # POST sem token
    r = requests.post(f"{BASE}/api/v1/reports/", json={})
    log_result("/api/v1/reports/", "POST", "Sem token", r.status_code, r.json(), 401)
    
    # POST body vazio
    r = requests.post(f"{BASE}/api/v1/reports/", json={}, headers=auth_header(admin_token))
    log_result("/api/v1/reports/", "POST", "Body vazio", r.status_code, r.json(), 422)
    
    # POST com turma_id inexistente (precisa de campos obrigatórios mínimos)
    r = requests.post(f"{BASE}/api/v1/reports/", json={
        "turma_id": fake_id,
        "disciplina_id": str(uuid.uuid4()),
        "data_aula": "2026-01-15",
        "horario_aula": "1º Horário",
        "conteudo_ministrado": "Teste",
        "estudio": "Estúdio 01",
    }, headers=auth_header(admin_token))
    log_result("/api/v1/reports/", "POST", "turma_id inexistente", r.status_code, r.json(), 404)
    
    # PATCH finalizar — relatório inexistente
    r = requests.patch(f"{BASE}/api/v1/reports/{fake_id}/finalizar", headers=auth_header(admin_token))
    log_result(f"/api/v1/reports/{{id}}/finalizar", "PATCH", "Relatório inexistente", r.status_code, r.json(), 404)
    
    # PATCH cancelar — relatório inexistente
    r = requests.patch(f"{BASE}/api/v1/reports/{fake_id}/cancelar", json={
        "justificativa": "Teste cancelamento"
    }, headers=auth_header(admin_token))
    log_result(f"/api/v1/reports/{{id}}/cancelar", "PATCH", "Relatório inexistente", r.status_code, r.json(), 404)
    
    # PATCH cancelar — sem justificativa
    r = requests.patch(f"{BASE}/api/v1/reports/{fake_id}/cancelar", json={}, headers=auth_header(admin_token))
    log_result(f"/api/v1/reports/{{id}}/cancelar", "PATCH", "Sem justificativa", r.status_code, r.json(), 422)
    
    # PUT editar — relatório inexistente
    r = requests.put(f"{BASE}/api/v1/reports/{fake_id}", json={
        "turma_id": fake_id,
        "disciplina_id": str(uuid.uuid4()),
        "data_aula": "2026-01-15",
        "horario_aula": "1º Horário",
        "conteudo_ministrado": "Teste",
        "estudio": "Estúdio 01",
    }, headers=auth_header(admin_token))
    log_result(f"/api/v1/reports/{{id}}", "PUT", "Relatório inexistente", r.status_code, r.json(), 404)
    
    # DELETE relatório inexistente
    r = requests.delete(f"{BASE}/api/v1/reports/{fake_id}", headers=auth_header(admin_token))
    log_result(f"/api/v1/reports/{{id}}", "DELETE", "Relatório inexistente", r.status_code, r.json(), 404)
    
    # Sync individual — inexistente
    r = requests.post(f"{BASE}/api/v1/reports/{fake_id}/sync-individual", headers=auth_header(admin_token))
    log_result(f"/api/v1/reports/{{id}}/sync-individual", "POST", "Relatório inexistente", r.status_code, r.json(), 404)
    
    # Stats sem token
    r = requests.get(f"{BASE}/api/v1/reports/stats")
    log_result("/api/v1/reports/stats", "GET", "Sem token", r.status_code, r.json(), 401)
    
    # Audit stats sem datas obrigatórias
    r = requests.get(f"{BASE}/api/v1/reports/audit-stats", headers=auth_header(admin_token))
    log_result("/api/v1/reports/audit-stats", "GET", "Sem datas obrigatórias", r.status_code, r.json(), 422)
    
    # Status semana sem parâmetros
    r = requests.get(f"{BASE}/api/v1/reports/status-semana", headers=auth_header(admin_token))
    log_result("/api/v1/reports/status-semana", "GET", "Sem parâmetros obrigatórios", r.status_code, r.json(), 422)


def test_grades(admin_token):
    """Testa cenários de erro das grades"""
    print("\n" + "="*70)
    print("📌 GRADES")
    print("="*70)
    
    fake_id = str(uuid.uuid4())
    
    # Upload sem token
    r = requests.post(f"{BASE}/api/v1/grades/upload")
    log_result("/api/v1/grades/upload", "POST", "Sem token", r.status_code, r.json(), 401)
    
    # Upload sem arquivo
    r = requests.post(f"{BASE}/api/v1/grades/upload", headers=auth_header(admin_token))
    log_result("/api/v1/grades/upload", "POST", "Sem arquivo", r.status_code, r.json(), 422)
    
    # Rascunhos sem token
    r = requests.get(f"{BASE}/api/v1/grades/rascunhos")
    log_result("/api/v1/grades/rascunhos", "GET", "Sem token", r.status_code, r.json(), 401)
    
    # Assistente tentando
    assistente_token = make_token_for_role("assistente", ADMIN_EMAIL)
    r = requests.get(f"{BASE}/api/v1/grades/rascunhos", headers=auth_header(assistente_token))
    log_result("/api/v1/grades/rascunhos", "GET", "Assistente tentando", r.status_code, r.json(), 403)
    
    # Editar rascunho inexistente
    r = requests.patch(f"{BASE}/api/v1/grades/rascunhos/{fake_id}", json={}, headers=auth_header(admin_token))
    log_result(f"/api/v1/grades/rascunhos/{{id}}", "PATCH", "Rascunho inexistente", r.status_code, r.json(), 404)
    
    # Publicar sem rascunhos
    r = requests.post(f"{BASE}/api/v1/grades/publish", json={
        "vigencia_inicio": "2026-01-01",
        "versao": "v1.0"
    }, headers=auth_header(admin_token))
    log_result("/api/v1/grades/publish", "POST", "Sem rascunhos para publicar", r.status_code, r.json(), 400)
    
    # Publicar sem campos obrigatórios
    r = requests.post(f"{BASE}/api/v1/grades/publish", json={}, headers=auth_header(admin_token))
    log_result("/api/v1/grades/publish", "POST", "Sem campos obrigatórios", r.status_code, r.json(), 422)


def test_external_api(admin_token):
    """Testa cenários de erro da API externa M2M"""
    print("\n" + "="*70)
    print("📌 API EXTERNA M2M (/api/v1/external)")
    print("="*70)
    
    fake_id = str(uuid.uuid4())
    
    # 1. Sem X-API-Key
    r = requests.get(f"{BASE}/api/v1/external/habilidades/por-ficheiro?report_id={fake_id}")
    log_result("/api/v1/external/habilidades/por-ficheiro", "GET", "Sem X-API-Key header", r.status_code, r.json(), 422,
               notes="Deveria ser 401/403 em vez de 422")
    
    # 2. X-API-Key inválida
    r = requests.get(f"{BASE}/api/v1/external/habilidades/por-ficheiro?report_id={fake_id}",
                     headers={"X-API-Key": "chave-invalida"})
    log_result("/api/v1/external/habilidades/por-ficheiro", "GET", "X-API-Key inválida", r.status_code, r.json(), 403)
    
    # 3. Sem report_id
    r = requests.get(f"{BASE}/api/v1/external/habilidades/por-ficheiro",
                     headers={"X-API-Key": "chave-invalida"})
    log_result("/api/v1/external/habilidades/por-ficheiro", "GET", "Sem report_id obrigatório", r.status_code, r.json(), 422)
    
    # 4. Habilidades por turma — sem turma_id
    r = requests.get(f"{BASE}/api/v1/external/habilidades/por-turma",
                     headers={"X-API-Key": "chave-invalida"})
    log_result("/api/v1/external/habilidades/por-turma", "GET", "Sem turma_id", r.status_code, r.json(), 422)
    
    # 5. Habilidades por disciplina — nome curto
    r = requests.get(f"{BASE}/api/v1/external/habilidades/por-disciplina?nome=X",
                     headers={"X-API-Key": "chave-invalida"})
    log_result("/api/v1/external/habilidades/por-disciplina", "GET", "Nome muito curto (min_length=2)", r.status_code, r.json(), 422)
    
    # 6. Habilidades por período — mês inválido
    r = requests.get(f"{BASE}/api/v1/external/habilidades/por-periodo?ano=2026&mes=13",
                     headers={"X-API-Key": "chave-invalida"})
    log_result("/api/v1/external/habilidades/por-periodo", "GET", "Mês 13 (inválido)", r.status_code, r.json(), 422)
    
    # 7. Ano muito baixo
    r = requests.get(f"{BASE}/api/v1/external/habilidades/por-periodo?ano=2019&mes=1",
                     headers={"X-API-Key": "chave-invalida"})
    log_result("/api/v1/external/habilidades/por-periodo", "GET", "Ano 2019 (< 2020)", r.status_code, r.json(), 422)


def test_live_monitor(admin_token):
    """Testa cenários de erro do live monitor"""
    print("\n" + "="*70)
    print("📌 LIVE MONITOR")
    print("="*70)
    
    # Sem token
    r = requests.get(f"{BASE}/api/v1/live/matrix")
    log_result("/api/v1/live/matrix", "GET", "Sem token", r.status_code, r.json(), 401)
    
    # Token expirado
    expired = make_expired_token()
    r = requests.get(f"{BASE}/api/v1/live/matrix", headers=auth_header(expired))
    log_result("/api/v1/live/matrix", "GET", "Token expirado", r.status_code, r.json(), 401)


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def generate_report():
    """Gera relatório consolidado."""
    total = len(results)
    ok = sum(1 for r in results if r["semantic_ok"])
    fail = total - ok
    
    print("\n\n")
    print("═" * 80)
    print("   📊 RELATÓRIO CONSOLIDADO DE TESTES DE ERRO")
    print("═" * 80)
    print(f"\n   Total de cenários testados: {total}")
    print(f"   ✅ Comportamento correto:    {ok}")
    print(f"   ❌ Inconsistências:           {fail}")
    print("─" * 80)
    
    if fail > 0:
        print("\n   ⚠️  INCONSISTÊNCIAS ENCONTRADAS:")
        print("─" * 80)
        for r in results:
            if not r["semantic_ok"]:
                print(f"\n   Endpoint: {r['endpoint']}")
                print(f"   Cenário:  {r['scenario']}")
                print(f"   Status:   {r['status']} (esperado: {r['expected']})")
                print(f"   Detalhe:  {r['detail']}")
                print(f"   Nota:     {r['notes']}")
                print("   " + "─" * 60)
    
    # Análise de padrões problemáticos
    print("\n\n   📋 ANÁLISE DE PADRÕES:")
    print("─" * 80)
    
    # Agrupar por status recebido
    status_map = {}
    for r in results:
        s = r["status"]
        if s not in status_map:
            status_map[s] = []
        status_map[s].append(r)
    
    for s in sorted(status_map.keys()):
        count = len(status_map[s])
        print(f"\n   HTTP {s}: {count} cenários")
    
    # Retornar dados para uso posterior
    return results


if __name__ == "__main__":
    print("🔍 Canal Educação v3.0 — Teste Exaustivo de Cenários de Erro")
    print(f"🌐 Base URL: {BASE}")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Verifica se o servidor está online
    try:
        r = requests.get(f"{BASE}/ping", timeout=5)
        print(f"✅ Servidor online: {r.json()}")
    except Exception as e:
        print(f"❌ Servidor não encontrado em {BASE}: {e}")
        exit(1)
    
    # Obtém token admin
    admin_token = get_admin_token()
    if not admin_token:
        print("❌ Não foi possível obter token do admin. Verifique as credenciais.")
        exit(1)
    print(f"🔑 Token admin obtido com sucesso")
    
    # Executa testes
    test_login()
    test_me(admin_token)
    test_me_theme(admin_token)
    test_invite(admin_token)
    test_confirm()
    test_forgot_password()
    test_reset_password()
    test_users(admin_token)
    test_force_reset(admin_token)
    test_audit_logs(admin_token)
    test_bootstrap(admin_token)
    test_cadastros(admin_token)
    test_turmas(admin_token)
    test_reports(admin_token)
    test_grades(admin_token)
    test_external_api(admin_token)
    test_live_monitor(admin_token)
    
    # Relatório final
    final_results = generate_report()
