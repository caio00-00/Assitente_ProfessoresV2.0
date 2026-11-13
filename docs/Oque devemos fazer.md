

# 📚 Documentação de Infraestrutura e Deploy - Oros Soluções

## 🎯 Objetivo Principal Atual
Subir as atualizações da branch `feature/atualizacoes-v3.0` para a branch `hml` (Homologação), configurar as variáveis de ambiente no **Dokploy**, executar os scripts de ETL no ambiente de homologação e garantir que a aplicação suba corretamente com **deploy automático a cada push**.

> ⚠️ **ATENÇÃO:** A branch `hml` **ainda não existe** no repositório remoto. O **Passo 0** abaixo trata disso antes de qualquer outra coisa.

---

## 🌐 1. Mapeamento de URLs e Domínios
Atualmente, apenas `hml-assistentes.orossolucoes.com.br` e `oroshub.orossolucoes.com.br` estão funcionando. O objetivo final é que todos os domínios abaixo estejam operacionais.

### 🏢 Sistema 01 (Oros Hub)
* **Produção (Frontend):** `oroshub.orossolucoes.com.br`
* **Produção (Backend):** `api.oroshub.orossolucoes.com.br`
* **Homologação (Frontend):** `hml.oroshub.orossolucoes.com.br`
* **Homologação (Backend):** `api-hml.orossolucoes.com.br`

### 🤖 Sistema 02 (Assistentes de Professores) - *Foco Atual*
* **Produção (Frontend):** `assistentes.orossolucoes.com.br`
* **Produção (Backend):** `api-assistentes.orossolucoes.com.br`
* **Homologação (Frontend):** `hml-assistentes.orossolucoes.com.br`
* **Homologação (Backend):** `api-hml-assistentes.orossolucoes.com.br`

### 📄 Página Fixa
* **Produção:** `portfolio.orossolucoes.com.br`

---

## 🔀 2. Estratégia de Branches (Git Flow Simplificado)

| Branch | Propósito | Deploy Automático |
|---|---|---|
| `feature/atualizacoes-v3.0` | Desenvolvimento ativo | ❌ Não |
| `hml` | Homologação / QA | ✅ Sim → `hml-assistentes.orossolucoes.com.br` |
| `prd` | Produção | ✅ Sim → `assistentes.orossolucoes.com.br` |

**Fluxo de trabalho:**
```
feature/atualizacoes-v3.0  →  hml  →  prd
         (dev)                (qa)    (prod)
```

Após esse deploy inicial, o fluxo de trabalho será:
1. Fazer alterações na branch `feature/atualizacoes-v3.0` (ou branches novas de feature)
2. Quando quiser subir para homologação: merge → `hml` → push → Dokploy faz deploy automático
3. Quando quiser subir para produção: merge → `prd` → push → Dokploy faz deploy automático

---

## 🧪 3. Ambiente de Homologação (HML) - *Foco Atual*

### 🐘 Banco de Dados: PostgreSQL (HML)
* **Serviço:** `postgres-hml`
* **Host Interno:** `assistente-professores-postgreshml-9fvdcy`
* **Porta Interna/Externa:** `5432`
* **Database:** `postgres-hml`
* **Usuário:** `assistente_professores`
* **Senha:** `nokgxwjh5bxkhuqr`
* **URL de Conexão Interna:** `postgresql://assistente_professores:<senha>@assistente-professores-postgreshml-9fvdcy:5432/postgres-hml`

### 🟥 Cache/Mensageria: Redis (HML)
* **Serviço:** `redis-hml`
* **Host Interno:** `assistente-professores-redishml-3p4fpc`
* **Porta Interna/Externa:** `6379`
* **Usuário:** `default`
* **Senha:** `6uk3ddy4mbsqwshj`
* **URL de Conexão Interna:** `redis://default:6uk3ddy4mbsqwshj@assistente-professores-redishml-3p4fpc:6379`

### ⚙️ Arquivo `.env` (Dokploy - HML)
*Nota: O erro de digitação `rredis://` foi corrigido para `redis://`.*

```env
# === Aplicacao ===
APP_NAME=Canal Educação API
APP_VERSION=3.0
DEBUG=True

# === URLs Base ===
FRONTEND_URL=https://hml-assistentes.orossolucoes.com.br
APP_URL=https://hml-assistentes.orossolucoes.com.br
BASE_URL=https://hml-assistentes.orossolucoes.com.br
API_URL=https://hml-assistentes.orossolucoes.com.br

# === Paths e Execução ===
PYTHONPATH=/app

# === Base de Dados (PostgreSQL) ===
POSTGRES_DB=postgres-hml
POSTGRES_USER=assistente_professores
POSTGRES_PASSWORD=<removido — ver o cofre de senhas / variáveis do Dokploy>
POSTGRES_HOST=assistente-professores-postgreshml-9fvdcy
POSTGRES_PORT=5432

# === Redis ===
REDIS_URL=redis://default:6uk3ddy4mbsqwshj@assistente-professores-redishml-3p4fpc:6379

# === Seguranca JWT ===
SECRET_KEY=<removido — ver o cofre de senhas / variáveis do Dokploy>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# === Tokens de Convite ===
INVITE_TOKEN_EXPIRE_HOURS=24

# === SMTP (Email Transacional) ===
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=paulosousacanal@gmail.com
SMTP_FROM_EMAIL=paulosousacanal@gmail.com
SMTP_PASSWORD=<removido — ver o cofre de senhas / variáveis do Dokploy>
SMTP_TLS=True

# === Dominios permitidos (vazio = qualquer email) ===
ALLOWED_EMAIL_DOMAINS=[]

# === CORS ===
#CORS_ORIGINS=["http://localhost:8000","http://localhost:3000"]

# === Google Drive ===
GOOGLE_DRIVE_VIDEOS_FOLDER_ID=id_pendente
GOOGLE_DRIVE_PDFS_FOLDER_ID=id_pendente
GOOGLE_APPLICATION_CREDENTIALS=credentials.json
```

---

## 🚀 4. Configurações Dokploy (Geral)
* **Provider:** Github (Account: `Dokploy-2026-03-24-zoef1f`)
* **Trigger Type:** `On Push` (Deploy automático ao fazer push na branch monitorada)
* **Build Type:** `Dockerfile` (Build Stage vazio - usa a última etapa do Dockerfile)
* **Build Path:** `/`
* **Docker Context Path:** `.`

> 💡 **O serviço HML no Dokploy deve estar acompanhando a branch `hml`.** Confirme isso no painel antes de executar o Passo 1.

---

## ⚠️ 5. Ambiente de Produção (PRD) - *Referência Futura*
*(Deixado documentado para quando a fase de homologação terminar)*

* **PostgreSQL (PRD):**
    * Host: `assistente-professores-postgrespdr-fzodnk`
    * DB: `postgres-pdr`
    * Senha: `w9JVkKytdirVgYh0ss9pv5p7eh0udkKTemwERQjpzt1cRJbLKEUYT5RJweAGDxfM2EnQKE`
* **Redis (PRD):**
    * Host: `assistente-professores-redispdr-b2pnzv`
    * Senha: `fgofpjrafmpleqdq`

---
---

## 📋 PLANO DE AÇÃO PASSO A PASSO (Para o Desenvolvedor)

Siga estas etapas no seu terminal local e no painel do Dokploy para concluir a atualização do ambiente de Homologação.

---

### 🆕 Passo 0: Sincronizar e Preparar a Branch `hml` (OBRIGATÓRIO)

> ⚠️ **A branch `hml` já existe no remoto, mas está com o histórico antigo.** Como queremos migrar a versão v3.0, precisamos "forçar" a atualização para que o remoto fique idêntico à sua atual feature branch.

No terminal, na pasta do projeto, execute:

```bash
# 1. Garanta que está na branch de feature com tudo atualizado
git checkout feature/atualizacoes-v3.0
git pull origin feature/atualizacoes-v3.0

# 2. Se a branch hml local já existir, delete-a para criar uma limpa
# (ignore o erro se ela não existir ainda)
git branch -D hml

# 3. Crie a branch hml a partir da feature
git checkout -b hml

# 4. Force o push para atualizar o remoto com a nova versão
git push -u origin hml --force
```

> ✅ O uso do `--force` é necessário neste caso porque vamos substituir o histórico antigo da HML pelo novo da v3.0. Após isso, o Dokploy disparará o primeiro build e deploy automaticamente.

---

### Passo 1: Como Fazer Atualizações Futuras (Fluxo Contínuo)

Após o Passo 0 ser feito uma vez, **toda vez que quiser subir novas alterações para HML**, o fluxo é:

```bash
# 1. Faça suas alterações na branch de feature
git checkout feature/atualizacoes-v3.0
# ... faça as alterações, commits, etc. ...
git push origin feature/atualizacoes-v3.0

# 2. Mude para a hml e atualize-a
git checkout hml
git pull origin hml

# 3. Faça o merge da feature para a hml
git merge feature/atualizacoes-v3.0

# 4. Envie as alterações → isso dispara o deploy automático no Dokploy
git push origin hml
```

> ✅ O `git push origin hml` dispara automaticamente o build e deploy no servidor via Dokploy.

---

### Passo 2: Configurar Variáveis de Ambiente no Dokploy

1. Acesse o painel do **Dokploy**.
2. Vá até o serviço **Sistema** (`assistente-professores-sistema-uqfbnd`).
3. Confirme que o serviço está configurado para monitorar a branch **`hml`**.
4. Navegue até a aba **Environment**.
5. Copie o bloco de código `.env` (da seção "Ambiente de Homologação (HML)" acima) e cole lá.
6. Se o Dokploy pedir variáveis em formato "Chave / Valor", adicione-as individualmente. Certifique-se de que a variável `PYTHONPATH` com o valor `/app` está presente.
7. Salve as alterações e reinicie a aplicação (se o Dokploy não fizer o re-deploy automático ao salvar as variáveis).

---

### Passo 3: Executar os Scripts de ETL

Como a aplicação está em contêineres gerenciados pelo Dokploy, você precisa acessar o terminal do contêiner da aplicação para rodar os scripts.

> ⚠️ **ATENÇÃO de PATH:** A pasta de scripts no repositório é `scripts/` (letra minúscula). No container Linux, o caminho correto é `/app/scripts/` (minúsculo). Usar `/app/Scripts/` (maiúsculo) causará erro.

**Opção A: Via Terminal do Dokploy (Mais fácil)**
1. No Dokploy, abra o serviço **Sistema**.
2. Vá até a aba **Terminal** (ou Logs > Exec).
3. Execute os scripts sequencialmente:

```bash
# Acesse a pasta raiz da aplicação (caso já não esteja)
cd /app

# Execute os scripts de ETL (nomes EXATOS dos arquivos no repositório)
python scripts/etl_professores.py
python scripts/etl_horarios.py
python scripts/etl_diretores_imagem_xlsx.py
```

> 💡 **Nota:** Não existe um script chamado `etl_disciplinas.py`. As disciplinas são gerenciadas pelo `etl_horarios.py` e pelo script `clean_disciplines.py` (limpeza). Se precisar executar limpeza de disciplinas duplicadas, use:
> ```bash
> python scripts/clean_disciplines.py
> ```

**Opção B: Via SSH no servidor (Se você tiver acesso root)**
```bash
# Liste os containers para achar o ID do container do Sistema (hml)
docker ps

# Entre no container
docker exec -it <ID_DO_CONTAINER_SISTEMA> /bin/bash

# Execute os scripts (atenção: pasta 'scripts' em minúsculo)
python /app/scripts/etl_professores.py
python /app/scripts/etl_horarios.py
python /app/scripts/etl_diretores_imagem_xlsx.py
```

---

### Passo 4: Validação

1. Aguarde o build do Dokploy terminar com sucesso (verifique os Logs do build).
2. Acesse `https://hml-assistentes.orossolucoes.com.br/`.
3. Verifique se as atualizações da v3.0 estão refletidas.
4. Faça login com uma conta de teste e valide:
   - Tela de Grade Horária
   - Formulário de Relatório
   - Live Monitor
   - Tela de Relatórios & Auditoria
5. Acesse os logs no Dokploy (Aba **Logs**) para garantir que não há erros de conexão com o PostgreSQL (`postgres-hml`) ou Redis (`redis-hml`).

---

## 📝 Referência dos Scripts Disponíveis

| Script | Descrição |
|---|---|
| `scripts/etl_professores.py` | Ingere dados de professores no banco |
| `scripts/etl_horarios.py` | Ingere grade horária e disciplinas |
| `scripts/etl_diretores_imagem_xlsx.py` | Ingere diretores de imagem do Excel |
| `scripts/etl_diretores.py` | Versão alternativa de ingestão de diretores |
| `scripts/clean_disciplines.py` | Limpa disciplinas duplicadas |
| `scripts/bootstrap.py` | Bootstrap inicial do sistema |
| `scripts/migrate_v3.py` | Migrações para v3 |
| `scripts/migrate_v3_diretores.py` | Migrações de diretores para v3 |