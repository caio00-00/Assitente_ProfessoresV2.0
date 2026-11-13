# Subir a v4 no Dokploy (HML primeiro, depois PRD)

A v4 foi feita para entrar no lugar da v3 **sem mudar a forma de deploy**: mesmo
`Dockerfile` na raiz, mesmo `docker-compose.yml` com os mesmos serviços
(`db`, `redis`, `api`, `worker`, `beat`) e o **mesmo volume do banco**
(`postgres_data_final`). O banco não é recriado: a migração só adiciona colunas e tabelas.

## Antes de subir

1. **Backup do banco de HML** (no servidor):
   ```bash
   bash scripts/dados_hml/exportar_hml.sh <container-postgres-hml>
   ```
   Guarde o `/tmp/hml_*.dump` até validar a v4.
2. Teste a v4 com os dados de HML no seu computador (`scripts/dados_hml/DADOS_HML.md`).

## Variáveis no Dokploy (aba Environment)

Confira as que já existem e acrescente as novas:

| Variável | Valor | Observação |
|---|---|---|
| `ENVIRONMENT` | `production` | **nova.** Fecha `/docs` e exige `SECRET_KEY` próprio |
| `SECRET_KEY` | a mesma de hoje | se trocar, todos precisam logar de novo |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | **os mesmos de hoje** | o compose novo lê do ambiente (antes estavam escritos no arquivo). `POSTGRES_DB` padrão continua `postgres-prd` |
| `REDIS_PASSWORD` | uma senha nova | **nova.** O Redis passa a exigir senha; o compose monta o `REDIS_URL` com ela |
| `RUN_MIGRATIONS` | `1` | padrão; a API aplica a migração da v4 ao subir |
| `LOGIN_MAX_ATTEMPTS` | `8` | opcional; `0` desliga o limite |
| `COMPLIANCE_MIN_VIDEO_MB` | `100` | opcional |
| `CELERY_VISIBILITY_TIMEOUT_SECONDS` | `43200` | opcional |

> `POSTGRES_PASSWORD` só vale na **criação** do volume. Com o volume antigo, o
> Postgres continua com a senha antiga — por isso use exatamente a de hoje.

## Diferenças que podem pegar no deploy

| O quê | Antes | Agora | Se precisar do jeito antigo |
|---|---|---|---|
| Portas do Postgres e Redis | abertas em todas as interfaces (`5432`, `6379`) | só `127.0.0.1` | se alguém acessa o banco de fora pelo IP público, use túnel SSH (recomendado) ou volte a porta para `"5432:5432"` |
| Redis | sem senha | com senha (`REDIS_PASSWORD`) | — |
| Comando da API | `uvicorn ... --reload` | `api-dev` (o mesmo uvicorn com reload) | para produção, troque por `api` (gunicorn com `WEB_CONCURRENCY` processos) quando estiver estável |
| Usuário no container | root | `app` (uid 1000) | a aplicação não grava em disco; não deve afetar |
| Comando próprio no Dokploy | — | se o Dokploy passar um comando completo (ex.: `uvicorn app.main:app ...`), o entrypoint executa esse comando e roda a migração antes | — |
| `/docs` da API | aberto | fechado com `ENVIRONMENT=production` | `DOCS_ENABLED=true` |

Se o Dokploy estiver configurado como **Application** (Dockerfile) e não como
**Compose**, nada disso muda: o `Dockerfile` sobe a API com gunicorn e prepara o banco.

## Subindo

1. Faça merge de `refactor/v4` na branch que o Dokploy de **HML** acompanha.
2. Deploy. Nos logs da API deve aparecer:
   ```
   [db_bootstrap] cenário do banco: marcado (...)
   Running upgrade h0i1j2k3l4m5 -> v4a1b2c3d4e5
   ```
3. Confira:
   - login de um assistente e de um diretor → caem no **Início**;
   - abrir a **Linha do tempo** de uma aula validada;
   - exportar a planilha de auditoria (coluna COBRAR);
   - `docker logs` do worker: tarefas recebidas sem erro.
4. Rode alguns dias em HML. Depois repita em PRD.

## Voltar para a v3

A migração não remove nada, então a v3 roda no banco migrado:
faça o deploy do commit anterior. As colunas e tabelas novas ficam lá, sem uso.
Para remover de vez: `alembic downgrade h0i1j2k3l4m5` (apaga o histórico de versões,
as tentativas de login e as justificativas de cancelamento).

Se voltar para a v3 e depois subir a v4 de novo, a API preenche sozinha, ao subir,
o `nome_normalizado` dos relatórios criados pela v3 nesse meio-tempo.

## Segurança — fazer mesmo sem a v4

O repositório da v3 tem senhas e chaves escritas em `docker-compose.yml` e em
`docs/Oque devemos fazer.md`, e elas continuam no histórico do Git. Troque:

- senha do Postgres de HML e de PRD;
- `SECRET_KEY` (desloga todo mundo uma vez);
- senha do SMTP e `EXTERNAL_API_KEY`.
