# Rodar a v4 na Vercel + Supabase (sem Docker)

O mesmo código roda nos dois lugares. Nada precisa ser trocado no código: a
Vercel define sozinha a variável `VERCEL=1`, e o sistema se ajusta.

| | Docker / Dokploy | Vercel |
|---|---|---|
| Banco | Postgres do compose (ou Supabase) | Supabase |
| Busca de vídeo e PDF no Drive | worker do Celery, sozinho, com tentativas a cada X min | roda na própria API: botão **Buscar no Drive**, **Reverificar** e um cron |
| Redis | sim | não usa |
| Tempo real na Grade (WebSocket) | sim | não — a grade atualiza ao abrir ou trocar de semana; o Ao vivo atualiza a cada 30 s |
| Migração do banco | automática ao subir o container | uma chamada à rota `/api/v1/sistema/migrar` (passo 5) |

## 1. Supabase: pegar as duas URLs do banco

No painel do Supabase: **Connect** (botão no topo) → **Connection string**.

- **Transaction pooler** (porta **6543**) → é a `DATABASE_URL` da Vercel.
- **Session pooler** (porta **5432**) → só para migrar. Se não informar, o sistema troca 6543 por 5432 sozinho.

Troque `[YOUR-PASSWORD]` pela senha do banco e acrescente `?sslmode=require` no fim:

```
postgresql://postgres.<projeto>:<senha>@aws-0-<regiao>.pooler.supabase.com:6543/postgres?sslmode=require
```

Se a senha tiver `@`, `#`, `/`, `%` ou `:`, escreva-os codificados (`@` = `%40`, `#` = `%23`, `/` = `%2F`, `%` = `%25`, `:` = `%3A`).

## 2. Vercel: criar o projeto

1. Suba a branch `refactor/v4` para o GitHub (`git push -u origin refactor/v4`).
2. Em vercel.com → **Add New… → Project** → escolha o repositório.
3. **Framework Preset:** FastAPI (ela detecta). Não mude build nem output.
4. Em **Root Directory** deixe a raiz do repositório.
5. Antes de clicar em Deploy, abra **Environment Variables** e preencha o passo 3.

A Vercel usa o `index.py` da raiz (que só importa `app.main:app`), o
`requirements.txt`, o `.python-version` (3.12) e o `vercel.json` (cron). O
`.vercelignore` deixa de fora testes, documentos, dumps e scripts soltos.

## 3. Variáveis de ambiente na Vercel

| Variável | Valor |
|---|---|
| `DATABASE_URL` | a URL do Transaction pooler (porta 6543) |
| `SECRET_KEY` | um texto longo e aleatório (o mesmo do HML, se quiser que os logins valham nos dois) |
| `ENVIRONMENT` | `production` |
| `CRON_SECRET` | outro texto aleatório, com 16+ caracteres. Protege o cron e a migração |
| `APP_DOMAIN` | o endereço do site, ex.: `https://canal-educacao.vercel.app` (vai nos e-mails de convite) |
| `CORS_ORIGINS` | o mesmo endereço |
| `GOOGLE_CREDENTIALS_B64` | o `credentials.json` em base64 (abaixo) |
| `GOOGLE_DRIVE_VIDEOS_FOLDER_ID`, `GOOGLE_DRIVE_PDFS_FOLDER_ID` | os mesmos do Docker |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` | os mesmos do Docker |
| `EXTERNAL_API_KEY` | a mesma do Docker, se a API externa for usada |
| `ALLOWED_EMAIL_DOMAINS` | opcional (vazio = qualquer e-mail) |
| `DATABASE_URL_MIGRACAO` | opcional: a URL do Session pooler (5432) |

Gerar o `GOOGLE_CREDENTIALS_B64` no PowerShell (copia para a área de transferência):

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("credentials.json")) | Set-Clipboard
```

Não precisa: `REDIS_URL`, `POSTGRES_*`, `PLATAFORMA` (a Vercel é detectada sozinha).

## 4. Deploy

Clique em **Deploy**. Quando terminar, abra `https://<seu-site>/api/v1/sistema/saude`.
Deve aparecer `"api": "ok"`, `"banco": "ok"`, `"plataforma": "vercel"`.

Se `"banco"` vier `"sem conexão"`, a `DATABASE_URL` está errada (senha, porta ou falta do `?sslmode=require`).

## 5. Criar as tabelas (uma vez) e o primeiro admin

No PowerShell, trocando o endereço, o segredo e os dados do admin:

```powershell
$site = "https://canal-educacao.vercel.app"
$segredo = "o-mesmo-CRON_SECRET-da-vercel"
$corpo = '{"primeiro_admin": {"email": "seu.email@empresa.com", "senha": "UmaSenhaForte123", "nome": "Seu Nome"}}'
Invoke-RestMethod -Method Post -Uri "$site/api/v1/sistema/migrar" -Headers @{ Authorization = "Bearer $segredo" } -ContentType "application/json" -Body $corpo
```

Resposta esperada: `ok: True`, `cenario: vazio`, `primeiro_admin: criado`.

- Se o Supabase já tiver os dados (ex.: importados do HML), o cenário é `marcado` ou `legado` e só as migrações novas rodam. O admin só é criado se o banco não tiver nenhum usuário.
- Depois de cada atualização do código que traga migração nova, rode de novo sem o `-Body`. Pode repetir quantas vezes quiser.

Entre no site com o e-mail e a senha do admin.

## 6. Busca automática no Drive

Na Vercel não há worker. A busca acontece:

- **Na hora**, pelos botões **Buscar no Drive** (tela Relatórios de aula) e **Reverificar** (num relatório).
- **Uma vez por dia**, pelo cron do `vercel.json` (09:00 UTC = 06:00 de Brasília). No plano gratuito (Hobby) a Vercel só permite cron diário.
- **Mais vezes, de graça**, com um agendador externo chamando a mesma rota. Exemplo com o cron-job.org:
  1. Crie uma conta e um *cronjob* novo.
  2. URL: `https://<seu-site>/api/v1/sistema/varredura`, a cada 30 minutos.
  3. Em **Advanced → Headers**, adicione `Authorization` com o valor `Bearer <CRON_SECRET>`.

Cada chamada verifica até onde der em ~50 segundos (`VARREDURA_TEMPO_MAX_SEGUNDOS`),
começando pelos relatórios há mais tempo sem verificação. As regras são as do worker:

- espera 2 h 30 depois de criar o relatório, para o arquivo chegar ao Drive;
- olha só as aulas dos últimos 45 dias;
- respeita o diretor de imagem (não busca antes de ele finalizar, nem com vídeo corrompido);
- marca Vermelho depois do tempo que as tentativas do worker levariam.

## 7. Voltar a rodar no Docker

Nada muda: `docker compose up` usa Celery, Redis e WebSocket como antes. Para
o Docker usar o mesmo Supabase da Vercel, veja `RODAR_LOCAL.md` (seção Supabase).
Não deixe o Docker com worker **e** a Vercel com cron rodando no mesmo banco ao
mesmo tempo: os dois buscariam no Drive os mesmos relatórios.

Para testar o modo da Vercel no Docker (sem worker), ponha no `.env`:

```
MODO_TAREFAS=direto
```

## Limites da Vercel que valem a pena saber

- Cada requisição tem tempo máximo. Exportações muito grandes (planilha de vários meses) podem passar do limite; se acontecer, exporte por períodos menores.
- O disco é só leitura; o sistema não grava arquivos (planilhas e PDFs são gerados em memória).
- Login e convites funcionam igual; os e-mails saem na hora (sem fila).
