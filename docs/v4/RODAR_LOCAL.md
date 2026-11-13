# Rodar a v4 no computador (Docker)

Precisa do **Docker Desktop** ligado. Os comandos são para o PowerShell, na pasta
`asssitentes_professores_v4`.

## 1. Configuração (uma vez)

```powershell
copy .env.example .env
notepad .env
```

No `.env`, troque pelo menos:

| Variável | Valor para o local |
|---|---|
| `POSTGRES_PASSWORD` | qualquer senha (é só do banco local) |
| `POSTGRES_DB` | `canal_local` |
| `SECRET_KEY` | qualquer texto longo |
| `ENVIRONMENT` | `development` |
| `POSTGRES_VERSION` | a versão do Postgres de HML, se for importar dados (padrão 15) |

**Google Drive:** coloque o `credentials.json` (conta de serviço) na raiz.
Se não for usar o Drive, crie um arquivo vazio com `{}` — sem o arquivo, o Docker
cria uma *pasta* com esse nome e o container não sobe.

```powershell
if (-not (Test-Path credentials.json)) { '{}' | Out-File -Encoding ascii credentials.json }
```

## 2. Subir

```powershell
docker compose up -d --build db redis api
docker compose logs -f api        # Ctrl+C para sair dos logs
```

Abra http://localhost:8000. Na primeira subida a API cria as tabelas sozinha.

O código em `app/` é recarregado ao salvar (modo desenvolvimento).

Para a busca automática no Drive e as rotinas noturnas, suba também:

```powershell
docker compose up -d worker beat
```

## 3. Primeiro usuário (banco vazio)

```powershell
docker compose exec api python -c "from app.core.database import SessionLocal; from app.models.user import User; from app.core.security import get_password_hash as h; db=SessionLocal(); db.add(User(email='admin@teste.local', full_name='Admin Local', role='admin', hashed_password=h('Teste@123'), email_confirmed=True)); db.commit(); print('ok')"
```

Login: `admin@teste.local` / `Teste@123`.

## 4. Com dados de HML

Veja `scripts/dados_hml/DADOS_HML.md`: exporta no servidor, importa aqui e
anonimiza nomes, e-mails e senhas. Depois todos entram com `Teste@123`.

## 5. Usando o Supabase em vez do Postgres local

No `.env`, defina a URL do *session pooler* (porta 5432) com SSL:

```
DATABASE_URL=postgresql://postgres.<projeto>:<senha>@aws-0-<regiao>.pooler.supabase.com:5432/postgres?sslmode=require
```

E suba com o outro arquivo:

```powershell
docker compose -f docker-compose.supabase.yml up -d --build api
```

A API aplica as migrações da v4 no Supabase ao subir (só adiciona colunas e tabelas).
Para não mexer no Supabase, deixe `RUN_MIGRATIONS=0` no `.env` — mas aí as telas
novas falham até a migração rodar.

## 6. Testes automatizados

```powershell
docker compose exec api python -m pytest -q
```

(313 testes; usam um SQLite em memória, não tocam no banco do Docker.)

> Os testes ficam fora da imagem (`.dockerignore`). Para rodar dentro do
> container, monte a pasta: `docker compose run --rm -v ${PWD}/tests:/app/tests api python -m pytest -q`.

## Comandos úteis

| Para | Comando |
|---|---|
| Ver o que está rodando | `docker compose ps` |
| Logs do worker | `docker compose logs -f worker` |
| Parar tudo | `docker compose down` |
| Apagar o banco local e começar do zero | `docker compose down -v` |
| Abrir o banco no DBeaver/pgAdmin | host `localhost`, porta `5432`, usuário/senha do `.env` |
| Rebuild depois de mudar `requirements.txt` | `docker compose up -d --build` |

## Se der erro

| Sintoma | Causa provável |
|---|---|
| `POSTGRES_PASSWORD ... defina no .env` | Falta o `.env` ou a variável |
| `credentials.json` é uma pasta | Apague a pasta, crie o arquivo (passo 1) |
| porta 5432 ou 8000 ocupada | Outro Postgres/serviço local; mude `POSTGRES_PORT_LOCAL` no `.env` ou pare o outro |
| `SECRET_KEY padrão` ao subir | `ENVIRONMENT=production` com a chave padrão; use `development` no local |
| tela em branco depois de atualizar | Ctrl+F5 (CSS e JS novos: `?v=4.0`) |
