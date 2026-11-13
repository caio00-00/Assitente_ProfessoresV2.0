# Guia de Instalação — Canal Educação v3.0

Guia completo e atualizado para inicializar o sistema do zero, rodar localmente com Docker, executar a carga inicial de dados (ETL) e colocar o projeto no ar.

> **Fonte da verdade:** Este guia reflete o estado real do código na branch `hml`. A documentação anterior estava desatualizada; este guia foi reescrito após validação completa do ambiente.

---

## Índice

1. [Pré-requisitos](#1-pré-requisitos)
2. [Obter o Código](#2-obter-o-código)
3. [Configurar o `.env`](#3-configurar-o-env)
4. [Subir o Ambiente Docker](#4-subir-o-ambiente-docker)
5. [Configuração Inicial e ETL](#5-configuração-inicial-e-etl)
6. [Validar o Sistema](#6-validar-o-sistema)
7. [Desenvolvimento Local (sem Docker)](#7-desenvolvimento-local-sem-docker)
8. [Deploy em VPS (Hostinger + Dokploy)](#8-deploy-em-vps-hostinger--dokploy)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Pré-requisitos

| Ferramenta | Versão mínima | Verificação |
|---|---|---|
| Docker Desktop | 24.x | `docker --version` |
| Docker Compose | v2 (plugin) | `docker compose version` |
| Git | qualquer | `git --version` |

> **Nota Windows:** Use PowerShell ou WSL2 para executar os comandos abaixo.

---

## 2. Obter o Código

```bash
git clone -b hml https://github.com/tioros/asssitentes_professores.git
cd asssitentes_professores
```

---

## 3. Configurar o `.env`

O arquivo `.env` já existe no repositório com valores funcionais para desenvolvimento local. **Não é necessário criar do zero.**

Variáveis principais que você pode querer ajustar:

```env
# Banco de dados (já configurado para Docker)
POSTGRES_USER=assistente_professores
POSTGRES_PASSWORD=<senha_forte>
POSTGRES_DB=postgres-prd

# A DATABASE_URL é construída automaticamente pelo config.py
# a partir das variáveis POSTGRES_* acima. Não precisa editar manualmente.

# Redis (já configurado para Docker)
REDIS_URL=redis://redis:6379/0

# JWT
SECRET_KEY=<troque_em_producao>
ACCESS_TOKEN_EXPIRE_MINUTES=300

# SMTP (opcional para dev local)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu@email.com
SMTP_PASSWORD=sua_app_password

# Google Drive (opcional para dev local)
GOOGLE_APPLICATION_CREDENTIALS=credentials.json
```

> **Importante:** As variáveis `POSTGRES_*` no `.env` devem ser idênticas às do serviço `db` no `docker-compose.yml`. Divergências causam erro de autenticação.

---

## 4. Subir o Ambiente Docker

### 4.1 Primeira execução (ambiente limpo)

```bash
docker compose up -d --build
```

Isso irá:
- Baixar as imagens `postgres:15` e `redis:7-alpine`
- Buildar a imagem Python da aplicação
- Inicializar o PostgreSQL com os usuários e banco configurados no `.env`
- Subir API, Worker, Beat, Redis e Banco

### 4.2 Verificar containers

```bash
docker compose ps
```

Saída esperada (todos `Up`):

```
NAME               STATUS
canal_edu_api      Up (healthy ou Up)
canal_edu_beat     Up
canal_edu_db       Up (healthy)
canal_edu_redis    Up
canal_edu_worker   Up
```

> O `canal_edu_db` demora alguns segundos para ficar `(healthy)`. Os outros serviços aguardam automaticamente.

---

## 5. Configuração Inicial e ETL

> **Atenção:** Execute cada comando **após** os containers estarem no status `Up`. O banco de dados é inicializado pelo próprio servidor FastAPI na primeira request (via `create_all`), mas os ETLs precisam das tabelas prontas.

### 5.1 Sincronizar o Alembic

O servidor cria as tabelas automaticamente no startup. Você precisa sincronizar o Alembic para que futuras migrations funcionem:

```bash
docker compose exec api alembic stamp head
```

> Este comando é necessário apenas **uma vez** por volume novo. Ele registra que o banco já está no estado mais recente sem recriar tabelas.

### 5.2 Executar os ETLs (ordem obrigatória)

**A) Professores, Disciplinas e Vínculos:**

```bash
docker compose exec api python scripts/etl_professores.py
```

Resultado esperado:
```
✅ ETL CONCLUÍDA COM SUCESSO!
👨‍🏫 Novos Professores: 55
📚 Novas Disciplinas: 72
🔗 Novos Vínculos: 143
```

**B) Grade Escolar, Turmas e Horários:**

```bash
docker compose exec api python scripts/etl_horarios.py --file horario.csv
```

Resultado esperado:
```
✅ Sucesso! Grades: 327, Turmas: 12
```

**C) Diretores de Imagem:**

```bash
docker compose exec api python scripts/etl_diretores_imagem_xlsx.py
```

Resultado esperado:
```
✅ ETL concluído com sucesso!
   📥 Novos diretores inseridos: 30
   ♻️ Já existentes (ignorados): 0
   📊 Total na tabela: 30
```

> O arquivo fonte é `data/diretores de imagem.xlsx`. O ETL é idempotente — rodar novamente não duplica registros.

**D) Limpeza de disciplinas órfãs (opcional — útil em re-runs):**

```bash
docker compose exec api python scripts/clean_disciplines.py
```

### 5.3 Criar o Usuário Admin (Bootstrap)

```bash
curl -X POST http://localhost:8000/api/v1/auth/bootstrap
```

Credenciais criadas:
- **Email:** `admin@canaleducacao.com`
- **Senha:** `admin123`

> Troque a senha imediatamente em ambiente de produção.

---

## 6. Validar o Sistema

### Health check da API

```bash
curl http://localhost:8000/ping
# {"status":"online","version":"3.0","app":"Canal Educação API"}
```

### Login (retorna JWT)

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@canaleducacao.com&password=admin123"
```

> **Atenção:** O login usa `Content-Type: application/x-www-form-urlencoded` com os campos `username` e `password` (padrão OAuth2), **não** JSON.

### Verificar dados no banco

```bash
docker exec canal_edu_db psql -U assistente_professores -d postgres-prd \
  -c "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"
```

### Interface web

Acesse `http://localhost:8000` no navegador.

### Interface Administrativa — Cadastros

Acesse `http://localhost:8000/admin/cadastros` para gerir os dados de referência do sistema. A página contém cinco abas:

| Aba | Descrição |
|---|---|
| 👨‍🏫 Professores | Listar, cadastrar, editar e ativar/inativar professores |
| 📚 Disciplinas | Listar, cadastrar, editar e ativar/inativar disciplinas |
| 🎓 Turmas | Listar e gerir as turmas cadastradas |
| 🎬 Diretores de Imagem | Listar, cadastrar, editar e ativar/inativar diretores de imagem |
| 🗓️ Gestão de Grades | Upload de nova grade horária via XLSX ou CSV |

#### 🎬 Diretores de Imagem

A aba exibe todos os diretores carregados pelo ETL, em ordem alfabética. Para cada registro é possível:

- **Ativar/Inativar** — clique no botão de status (`✅ Ativo` / `⛔ Inativo`) para alternar o estado sem excluir o registro. Use o checkbox **"Mostrar inativos"** para visualizar registros desativados.
- **Editar nome** — botão `✏️` na coluna "Ações".
- **Cadastrar novo** — botão `+ Novo Diretor` no topo da lista.

Para carregar a lista completa a partir do Excel (`data/diretores de imagem.xlsx`):

```bash
docker compose exec api python scripts/etl_diretores_imagem_xlsx.py
```

#### 🗓️ Gestão de Grades

A aba oferece uma área de **drag-and-drop** (ou clique para selecionar) para enviar uma nova grade horária nos formatos `.xlsx` ou `.csv`. O sistema processa o arquivo e popula as tabelas de grades, turmas e horários.

Para carregar a grade pela linha de comando (alternativa ao upload pela interface):

```bash
docker compose exec api python scripts/etl_horarios.py --file horario.csv
```

---

## 7. Desenvolvimento Local (sem Docker)

Para rodar a API fora do Docker (conectando ao PostgreSQL no Docker via `localhost:5432`):

```bash
# 1. Crie e ative o virtualenv
python -m venv venv
.\venv\Scripts\activate        # Windows
source venv/bin/activate       # Linux/Mac

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Suba apenas banco e Redis
docker compose up -d db redis

# 4. Inicie a API localmente
uvicorn app.main:app --reload --port 8000
```

> O `config.py` detecta automaticamente que está fora do Docker e usa `localhost` em vez de `db` como host do banco.

---

## 8. Deploy em VPS (Hostinger + Dokploy)

### Passo 1: Preparar a VPS

1. Adquira um plano KVM 2 ou superior na [Hostinger](https://www.hostinger.com.br/vps-hosting).
2. Configure o SO como **Ubuntu 22.04 LTS**.
3. Libere as portas `80`, `443` e `22` no firewall.
4. Acesse via SSH: `ssh root@<IP_VPS>`

### Passo 2: Instalar o Dokploy

```bash
curl -sSL https://dokploy.com/install.sh | sh
```

Após 3–5 minutos, acesse: `http://<IP_VPS>:3000`

### Passo 3: Criar Projeto e Configurar Compose

1. Crie um novo **Project** no Dokploy.
2. Adicione um **Compose** vinculado ao repositório `https://github.com/tioros/asssitentes_professores.git` (branch `hml`).
3. Na aba **Environment (.env)**, configure as variáveis sensíveis:
   - `POSTGRES_PASSWORD` (use uma senha forte e diferente do dev)
   - `SECRET_KEY` (gere com `openssl rand -hex 32`)
   - `GOOGLE_DRIVE_VIDEOS_FOLDER_ID`
   - `GOOGLE_DRIVE_PDFS_FOLDER_ID`
4. Faça o **Deploy**.

### Passo 4: Pós-deploy — ETL em Produção

No terminal interno do Dokploy (ou via `docker exec`):

```bash
docker compose exec api alembic stamp head
docker compose exec api python scripts/etl_professores.py
docker compose exec api python scripts/etl_horarios.py --file horario.csv
curl -X POST http://localhost:8000/api/v1/auth/bootstrap
```

### Passo 5: Configurar Domínio com HTTPS

1. No DNS do seu domínio, crie um registro `A` apontando para o IP da VPS.
2. No Dokploy, adicione o domínio ao serviço `api` e ative **"Generate Let's Encrypt / SSL"**.

---

## 9. Troubleshooting

### ❌ `FATAL: password authentication failed for user "assistente_professores"`

**Causa:** O volume Docker `postgres_data_final` foi inicializado com credenciais diferentes. O PostgreSQL ignora as variáveis de ambiente quando o data directory já existe.

**Solução (dados de dev — volume vazio):**

```bash
# 1. Pare os containers
docker compose down

# 2. Remova o volume com credenciais obsoletas
docker volume rm asssitentes_professores_postgres_data_final

# 3. Suba tudo do zero
docker compose up -d --build
```

> **Antes de dropar o volume**, verifique se há dados importantes:
> ```bash
> docker exec canal_edu_db psql -U <usuario_atual> -d <db_atual> \
>   -c "SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE n_live_tup > 0;"
> ```

### ❌ `FATAL: role "assistente_professores" does not exist`

Mesma causa do erro acima. O volume foi criado com um usuário diferente. Siga a solução de reset do volume.

### ❌ `DuplicateTable` ao rodar `alembic upgrade head`

**Causa:** A aplicação usa `Base.metadata.create_all()` no startup, criando as tabelas antes do Alembic.

**Solução:** Use `stamp` em vez de `upgrade`:

```bash
docker compose exec api alembic stamp head
```

### ❌ `relation "alembic_version" does not exist` no Alembic

O banco foi criado via `create_all()` sem ter rodado as migrations. Use `alembic stamp head` conforme o passo 5.1.

### ❌ API não conecta ao banco (container sobe mas logs mostram erro de conexão)

Verifique se o PostgreSQL passou para `(healthy)`:

```bash
docker compose ps
```

Se o `canal_edu_db` estiver em `starting` ou `unhealthy`:

```bash
docker compose logs db
```

O `api` só inicia após o `db` ficar `(healthy)` — aguarde ou reporte o erro dos logs do banco.

### ❌ Celery Worker mostra warning sobre `broker_connection_retry_on_startup`

Esse é um **aviso de depreciação** do Celery para a versão 6.0, não um erro. O worker está funcionando normalmente. Para suprimir, adicione ao `docker-compose.yml` nas variáveis do worker:

```yaml
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP: "true"
```

### ❌ Login retorna `{"detail":"Field required"}`

O endpoint de login usa OAuth2 form data, **não JSON**. Use:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=email@exemplo.com&password=senha"
```

---

## Checklist de Instalação Completa

- [ ] Docker Desktop rodando
- [ ] `docker compose up -d --build` — todos containers `Up`
- [ ] `docker compose ps` — `canal_edu_db` está `(healthy)`
- [ ] `docker compose exec api alembic stamp head` — saída: `(head)`
- [ ] `docker compose exec api python scripts/etl_professores.py` — sucesso
- [ ] `docker compose exec api python scripts/etl_horarios.py --file horario.csv` — sucesso
- [ ] `docker compose exec api python scripts/etl_diretores_imagem_xlsx.py` — 30 diretores inseridos
- [ ] `curl -X POST http://localhost:8000/api/v1/auth/bootstrap` — admin criado
- [ ] `curl http://localhost:8000/ping` — `{"status":"online"}`
- [ ] Login em `http://localhost:8000` com `admin@canaleducacao.com` / `admin123`
- [ ] `http://localhost:8000/admin/cadastros` → aba "Diretores de Imagem" exibe os 30 registros
