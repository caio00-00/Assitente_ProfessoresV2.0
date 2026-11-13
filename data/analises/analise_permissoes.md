# Análise de Permissões e Segurança (RBAC)

Este documento destrincha o modelo de controle de acesso (Roles/Perfis) adotado pelo "Canal Educação", avaliando o Modelo de Autenticação (`user.py`), as Seguranças Backend (`deps.py`) e as restrições de Front-End nativas da aplicação.

---

## 👥 1. Níveis de Acesso (Roles) Existentes
A aplicação não possui uma tabela em banco separada para mapear permissões complexas. A role (perfil) está tipada de maneira direta (String) na tabela `users` (`app/models/user.py`):
`role = Column(String(50), default="assistente", nullable=False)`

Inspecionando os arquivos de dependência API (`deps.py`) e de roteamento assíncrono do JS (`app.js`), validou-se a presença e o uso prático de **3 Perfis Base**:
1. **admin** (Superusuário, gerencia times, acesso total)
2. **gestor** (Gerência local, mesma visualização do admin para certas abas NOC)
3. **assistente** (Operador padrão da ponta, restrito via código aos próprios relatórios)

---

## 🗺️ 2. Matriz de Autorização do Módulo Frontend

Abaixo se encontra o mapa de navegação das páginas listadas no `base.html` (Barra Lateral Esquerda) e quem as visualiza:

| Visão do Menu / Template Mapeado | Rota URI | `admin` | `gestor` | `assistente` |
|-----------------------------------|----------|---------|----------|--------------|
| **Dashboard** (`dashboard.html`) | `/dashboard` | ✅ Livre | ✅ Livre | ✅ Livre |
| **Nova Aula** (`report_form.html`) | `/report` | ✅ Livre | ✅ Livre | ✅ Livre (Mas restrito no backend a não alterar aula de outros) |
| **Grade Horária** (`grade.html`) | `/grade` | ✅ Livre | ✅ Livre | ✅ Livre |
| **Relatórios & Auditoria** | `/reports-audit` | ✅ Livre | ✅ Livre | ✅ Livre |
| **Live Monitor** (`live_monitor.html`)| `/live-monitor` | ✅ Livre | ✅ Livre | ✅ Livre |
| **Utilizadores (Setor Admin)** | `/admin/users` | ✅ Livre | ✅ Livre | ❌ **Negado** |

---

## 🔐 3. Análise de Bloqueio Jinja2 vs JavaScript (Segurança de Tela)

A requisição solicitou investigar se existia alguma regra de processamento no back-end (Server-Side com Jinja2, ex: `{% if current_user.role == 'admin' %}`) forçando a ausência segura do botão de "Utilizadores" no `base.html`.

**Veredito: Não existem bloqueios via Jinja2 ❌**

Todo o mecanismo de exibição e bloqueio do menu está implementado de maneira **reativa no Front-End** (via Vanilla JavaScript). 

Ocultação do Menu (`app/static/js/app.js`):
```javascript
const adminNav = document.getElementById('nav-admin');
if (adminNav && !['admin', 'gestor'].includes(user.role)) {
    adminNav.style.display = 'none'; // Aplica CSS para ficar invisível
}
```

### ⚠️ Observação sobre Risco de Segurança Visual
Como o backend não oculta a *String* HTML do botão da tela se você for assistente, um assistente mal-intencionado com conhecimento técnico básico pode usar o `Configurar Elemento` (F12) do navegador e desmarcar o `display: none` para ver a interface da tela de "Utilizadores" (`/admin/users`). 
Entretanto, testamos isso e não há risco crítico de quebras de sigilo, haja visto que o arquivo de dependências da API Backend (`app/api/deps.py -> require_role('admin')`) rejeitará quaisquer submissões feitas via API gerando um Erro **403 Forbidden** na tentativa de deletar ou listar os usuários. Mas a título do primor, seria sim salutar reescrever o menu trocando o JS pelo tag do `Jinja2` visando sumir fisicamente com o código dom.
