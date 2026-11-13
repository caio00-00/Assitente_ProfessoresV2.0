# Canal Educação — Assistente de Professores v3.0

Sistema web completo para gestão de relatórios de aula, grade horária, monitoramento em tempo real e conformidade com Google Drive. Desenvolvido para a OROS Educação.

---

## Funcionalidades

| Módulo | Descrição |
|---|---|
| **Relatório de Aula** | Formulário completo para registro de cada aula: turma, disciplina, professor, estúdio, horário, conteúdo, recursos utilizados, ocorrências e campos BNCC |
| **Grade Horária** | Visualização da grade semanal por turma, exibindo todas as aulas, professores e horários |
| **Relatórios & Auditoria** | Listagem, filtros e auditoria de todos os relatórios com trilha de ações |
| **Live Monitor** | Painel NOC em tempo real via WebSocket mostrando o status de cada estúdio e aula em andamento |
| **Gestão de Cadastros** | CRUD completo de Professores, Disciplinas, Turmas, Diretores de Imagem e upload de grade horária |
| **Gestão de Usuários** | Criação, edição e controle de acesso por papel (Admin, Professor, etc.) |
| **Conformidade Drive** | Verificação automática em background de vídeos e slides no Google Drive, vinculando-os ao relatório |
| **Notificações por E-mail** | Envio automático de e-mails de confirmação, redefinição de senha e alertas |
| **Relatório do Diretor de Imagem** (v3.2) | Tela restrita para Diretores de Imagem preencherem o acompanhamento técnico do turno no estúdio (aulas, checklist de fechamento, perguntas extras cadastráveis pelo Diretor-Chefe) e exportarem em PDF |

---

## v3.2 — Relatório do Diretor de Imagem

Tela nova (`/diretor-imagem`), parecida com a de Relatório de Aula, mas restrita aos papéis `diretor_imagem`, `diretor_chefe`, `gestor` e `admin`.

- **Cabeçalho automático**: diretor, data, turno, estúdio, série/turma, horário de entrada/saída e link do YouTube — com botão para puxar automaticamente as aulas já lançadas no Relatório de Aula daquele turno/estúdio/data.
- **Blocos "AULA 0X"**: disciplina, professor e os 6 campos técnicos fixos do relatório em papel (transmissão/gravada, vídeo corrompido, interrupções, problema de áudio, vinhetas, créditos) + observações livres.
- **Checklist de fechamento de estúdio**: itens configuráveis (ex.: microfone, caneta, controle da TV), cadastrados pelo Diretor-Chefe em `/diretor-imagem/perguntas`.
- **Perguntas extras**: o Diretor-Chefe cadastra perguntas adicionais (Sim/Não ou texto livre), escolhendo se aparecem uma vez por relatório ou repetidas em cada bloco de aula.
- **Exportação em PDF**: botão "Baixar PDF" gera o relatório no layout do modelo em papel (via `xhtml2pdf`, sem dependências de sistema).
- **Histórico**: `/diretor-imagem/historico` lista os relatórios já lançados, com filtros e download do PDF.

### Papéis novos

| Papel | Pode |
|---|---|
| `diretor_imagem` | Criar/editar/finalizar e baixar em PDF os **próprios** relatórios |
| `diretor_chefe` | Tudo do `diretor_imagem` + ver/gerir os relatórios de **todos** os diretores + cadastrar perguntas extras e itens de checklist |

Um cadastro em **Diretores de Imagem** (`/admin/cadastros`) agora pode ser vinculado a um usuário com login (campo "Usuário vinculado"), para que aquele diretor consiga acessar o próprio relatório. Convide o usuário normalmente em `/admin/users` com o perfil "Diretor de Imagem" e depois faça o vínculo em Cadastros → Diretores de Imagem.

### Migração de banco de dados

A migração `c9f1a2b3d4e5_diretor_imagem_report.py` cria as tabelas `image_director_reports`, `image_director_lessons`, `image_director_checklist_items`, `image_director_checklist_responses`, `image_director_custom_questions`, `image_director_custom_answers`, e adiciona a coluna `user_id` em `diretores_imagem`. Rode:

```bash
docker compose exec api alembic upgrade head
```

---

## Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| **Backend** | Python 3.11+, FastAPI 0.109, SQLAlchemy 2.0 |
| **Banco de Dados** | PostgreSQL 15 |
| **Fila / Cache** | Redis 7 + Celery 5.3 |
| **Frontend** | Jinja2 Templates + JavaScript (sem framework pesado) |
| **Auth** | JWT (python-jose) + bcrypt, OAuth2 Password Flow |
| **Integrações** | Google Drive API v3 |
| **Migrações** | Alembic |
| **Containers** | Docker + Docker Compose |
| **Deploy** | Dokploy (VPS Hostinger) |

---

## Arquitetura

```
┌─────────────────────────────────────────────────┐
│                   Docker Compose                │
│                                                 │
│  ┌──────────┐    ┌──────────┐    ┌───────────┐  │
│  │  canal_  │    │  canal_  │    │  canal_   │  │
│  │  edu_api │    │  edu_    │    │  edu_beat │  │
│  │ :8000    │    │  worker  │    │ (scheduler│  │
│  └────┬─────┘    └────┬─────┘    └─────┬─────┘  │
│       │               │                │        │
│  ┌────▼───────────────▼────────────────▼──────┐  │
│  │          canal_edu_redis :6379             │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │          canal_edu_db (PostgreSQL) :5432   │  │
│  └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

- **api**: Servidor FastAPI (uvicorn, hot-reload em dev)
- **worker**: Celery worker — processa conformidade com Google Drive em background
- **beat**: Celery Beat — agendador de tarefas periódicas (reprocessamento a cada 2h)
- **redis**: Broker do Celery e cache
- **db**: PostgreSQL — fonte de verdade de todos os dados

---

## Início Rápido (Docker)

### Pré-requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 24+
- Git

### 1. Clonar o repositório

```bash
git clone -b hml https://github.com/tioros/asssitentes_professores.git
cd asssitentes_professores
```

### 2. Subir os containers

```bash
docker compose up -d --build
```

Aguarde todos os serviços ficarem `Up`:

```bash
docker compose ps
```

```
canal_edu_api      Up
canal_edu_beat     Up
canal_edu_db       Up (healthy)
canal_edu_redis    Up
canal_edu_worker   Up
```

### 3. Sincronizar migrações

```bash
docker compose exec api alembic stamp head
```

> Necessário apenas uma vez por volume novo. O banco é criado automaticamente no startup via `create_all`.

### 4. Carregar os dados (ETLs)

```bash
# Professores, disciplinas e vínculos
docker compose exec api python scripts/etl_professores.py

# Grade horária, turmas e horários
docker compose exec api python scripts/etl_horarios.py --file horario.csv

# Diretores de imagem
docker compose exec api python scripts/etl_diretores_imagem_xlsx.py
```

### 5. Criar o usuário admin

```bash
curl -X POST http://localhost:8000/api/v1/auth/bootstrap
```

Credenciais criadas:
- **Email:** `admin@canaleducacao.com`
- **Senha:** `admin123`

> Troque a senha em produção.

### 6. Acessar o sistema

Abra `http://localhost:8000` no navegador.

---

## Páginas do Sistema

| URL | Descrição |
|---|---|
| `/` | Login |
| `/dashboard` | Dashboard principal |
| `/report` | Formulário de novo relatório de aula |
| `/grade` | Grade horária semanal |
| `/reports-audit` | Relatórios e auditoria |
| `/live-monitor` | Painel NOC em tempo real |
| `/diretor-imagem` | Relatório do Diretor de Imagem (v3.2) |
| `/diretor-imagem/historico` | Histórico do Relatório do Diretor de Imagem |
| `/diretor-imagem/perguntas` | Administração de perguntas extras e checklist (Diretor-Chefe) |
| `/admin/cadastros` | Cadastros (professores, disciplinas, turmas, diretores, grades) |
| `/admin/users` | Gestão de usuários |
| `/docs` | Documentação interativa da API (Swagger UI) |
| `/redoc` | Documentação ReDoc |

---

## Variáveis de Ambiente

O arquivo `.env` está presente no repositório com valores para desenvolvimento. As principais variáveis:

```env
# Banco de dados
POSTGRES_USER=assistente_professores
POSTGRES_PASSWORD=<senha_forte>
POSTGRES_DB=postgres-prd

# Redis
REDIS_URL=redis://redis:6379/0

# JWT — troque em produção
SECRET_KEY=<string_aleatoria_longa>
ACCESS_TOKEN_EXPIRE_MINUTES=300

# Google Drive (necessário para compliance de vídeos/slides)
GOOGLE_APPLICATION_CREDENTIALS=credentials.json
GOOGLE_DRIVE_VIDEOS_FOLDER_ID=<id_pasta_drive>
GOOGLE_DRIVE_PDFS_FOLDER_ID=<id_pasta_drive>

# SMTP (opcional para dev local)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu@email.com
SMTP_PASSWORD=sua_app_password
```

> `credentials.json` e `credentials2.json` são as credenciais da conta de serviço do Google. **Não devem ser commitados em repositórios públicos.**

---

## Estrutura do Projeto

```
asssitentes_professores/
│
├── app/                        # Aplicação FastAPI
│   ├── api/                    # Rotas e handlers
│   │   ├── rotas_auth.py       # Autenticação e JWT
│   │   ├── rotas_report.py     # CRUD de relatórios de aula
│   │   ├── rotas_grade.py      # API da grade horária
│   │   ├── rotas_cadastros.py  # CRUD administrativo
│   │   ├── rotas_live.py       # Live Monitor
│   │   ├── rotas_turma.py      # Turmas
│   │   └── websocket/          # WebSocket (grade e live)
│   ├── core/                   # Config, DB, segurança, Celery
│   ├── domain/                 # Exceções e enums de negócio
│   ├── models/                 # Modelos SQLAlchemy
│   ├── schemas/                # Schemas Pydantic (DTOs)
│   ├── services/               # Lógica de negócio (Drive, e-mail, naming)
│   ├── static/                 # CSS e JavaScript
│   ├── tasks/                  # Tarefas Celery (compliance Drive)
│   ├── templates/              # Templates Jinja2 (HTML)
│   └── main.py                 # Entry point FastAPI
│
├── alembic/                    # Migrações de banco de dados
├── data/                       # Arquivos de dados para ETL (xlsx, csv)
├── docs/                       # Documentação interna
├── scripts/                    # ETLs e scripts utilitários
├── tests/                      # Suite de testes (pytest)
│
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
├── requirements.txt
└── alembic.ini
```

---

## Scripts Disponíveis

Todos os scripts devem ser executados dentro do container:

```bash
docker compose exec api python scripts/<script>.py
```

| Script | Descrição |
|---|---|
| `etl_professores.py` | Importa professores, disciplinas e vínculos do Excel |
| `etl_horarios.py` | Importa grade horária, turmas e horários do CSV/XLSX |
| `etl_diretores_imagem_xlsx.py` | Importa diretores de imagem do Excel |
| `import_bncc.py` | Importa habilidades BNCC do JSON |
| `bootstrap.py` | Cria o usuário admin inicial |
| `sanitizar_banco.py` | Limpeza e saneamento de dados inconsistentes |
| `migrate_v3.py` | Migração de dados para a versão 3.0 |

---

## API

A API REST completa está disponível em `/docs` (Swagger UI) após subir os containers.

Autenticação via OAuth2 Password Flow:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@canaleducacao.com&password=admin123"
```

> O endpoint usa `application/x-www-form-urlencoded`, **não** JSON.

Health check:

```bash
curl http://localhost:8000/ping
# {"status":"online","version":"3.0","app":"Canal Educação API"}
```

---

## Testes

```bash
docker compose exec api pytest tests/ -v
```

---

## Deploy em Produção

O projeto está configurado para deploy via **Dokploy** em VPS Hostinger. Consulte [`docs/GUIA_INSTALACAO.md`](docs/GUIA_INSTALACAO.md) para o guia completo, incluindo:

- Configuração do Dokploy e Docker Swarm
- Variáveis de ambiente em produção
- ETLs pós-deploy
- Configuração de domínio com HTTPS (Let's Encrypt)

---

## Troubleshooting

| Erro | Causa | Solução |
|---|---|---|
| `FATAL: password authentication failed` | Volume Postgres inicializado com credenciais antigas | `docker compose down && docker volume rm asssitentes_professores_postgres_data_final && docker compose up -d --build` |
| `DuplicateTable` no alembic | `create_all` criou as tabelas antes do Alembic | Use `alembic stamp head` em vez de `alembic upgrade head` |
| Grade horária vazia | ETLs não foram rodados no ambiente | Execute os ETLs conforme a seção "Início Rápido" |
| Login retorna `Field required` | Enviando JSON em vez de form-urlencoded | Use `Content-Type: application/x-www-form-urlencoded` |

---

## Licença

Projeto proprietário — OROS Educação. Todos os direitos reservados.
