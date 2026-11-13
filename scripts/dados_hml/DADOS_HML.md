# Dados de HML no Docker local

Traz uma cópia do banco de HML para o Postgres local e **anonimiza na hora**:
nomes, e-mails e senhas trocados antes de você abrir o sistema.

## Em 4 passos

**1. No servidor (SSH), gere o dump** — só leitura, nada muda em HML:

```bash
# copie o script para o servidor uma vez
scp scripts/dados_hml/exportar_hml.sh <usuario>@<servidor>:~/

ssh <usuario>@<servidor>
bash exportar_hml.sh                 # mostra os containers Postgres
bash exportar_hml.sh <container-hml> # gera /tmp/hml_AAAAMMDD_HHMM.dump
```

O script mostra a versão do Postgres de HML. Coloque a mesma no `.env` local
(`POSTGRES_VERSION=15`, por exemplo): o `pg_restore` não lê dump de versão mais nova.

**2. Baixe para a pasta `scripts/dados_hml/`** e apague do servidor:

```powershell
scp <usuario>@<servidor>:/tmp/hml_20261111_1030.dump .\scripts\dados_hml\
ssh <usuario>@<servidor> "rm /tmp/hml_20261111_1030.dump"
```

**3. Importe e anonimize** (apaga e recria o banco local):

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File .\scripts\dados_hml\importar_hml.ps1 -Arquivo .\scripts\dados_hml\hml_20261111_1030.dump
```
```bash
# Linux / macOS / Git Bash
bash scripts/dados_hml/importar_hml.sh scripts/dados_hml/hml_20261111_1030.dump
```

O dump com dados reais é apagado no fim. Use `-ManterDump` / `--manter-dump` se quiser guardá-lo.

**4. Suba a API** — ela aplica as migrações da v4 sozinha:

```powershell
docker compose up -d api
```

Abra http://localhost:8000 e entre com **admin@teste.local / Teste@123**.

## Logins depois da importação

Todos os usuários ficam com a senha **Teste@123** e o e-mail confirmado.
O e-mail segue o papel e a ordem de cadastro:

| Papel | Exemplo de login |
|---|---|
| admin (o mais antigo) | `admin@teste.local` |
| outros admins | `admin002@teste.local` |
| assistente | `assistente001@teste.local`, `assistente002@teste.local`… |
| coordenador | `coordenador001@teste.local` |
| diretor de imagem | `diretor_imagem001@teste.local` |
| diretor-chefe | `diretor_chefe001@teste.local` |
| gestor, auditor | `gestor001@teste.local`, `auditor001@teste.local` |

O fim da importação imprime a lista real (papel, quantidade, primeiro login).

## O que a anonimização troca

| Onde | Vira |
|---|---|
| `users` | e-mail `<papel>NNN@teste.local`, nome `<Papel> NNN`, senha `Teste@123`, convites e links de reset apagados |
| `professores` | `Professor 0001`, `Professor 0002`… — o mesmo nome novo é aplicado nas aulas do diretor de imagem, então os pares continuam batendo |
| nome de professor externo / substituto | `Professor externo` |
| `diretores_imagem` | `Diretor de imagem 01`… (o usuário ligado recebe o mesmo nome) |
| agenda: autor, criado por, responsável do evento | nome anonimizado do usuário / `Responsável do evento` |
| `audit_logs`, `login_attempts`, `report_versions` | esvaziadas (guardam e-mails, IPs e cópias completas) |

**Não muda:** turmas, disciplinas, grade, estúdios, datas, status, links do Drive/YouTube,
conteúdo e observações das aulas — é isso que o teste precisa.
Campos de texto livre (observações) podem citar nomes; não compartilhe o banco local.

O script confere no fim que nenhum e-mail fora de `@teste.local` sobrou e desfaz tudo se sobrar.

## Cuidados

- **Worker e beat ligados usam o Drive de verdade.** Com `credentials.json` presente,
  o worker local busca vídeos e PDFs no Drive (só leitura) e grava os links no banco
  local. Para testar só a tela, suba apenas `db redis api`.
- Os arquivos `*.dump`, `*.sql` e `*.sql.gz` desta pasta estão no `.gitignore` — não
  dá para subir um dump real para o Git por engano (exceto `anonimizar.sql`, que é o script).
- O `anonimizar.sql` se recusa a rodar fora de um banco chamado `canal_local` /
  `canal_hml_local`, para ninguém rodar no HML por engano.

## Se der erro

| Mensagem | O que fazer |
|---|---|
| `unsupported version (1.15) in file header` | O HML é de versão mais nova: ajuste `POSTGRES_VERSION` no `.env`, rode `docker compose down -v` e importe de novo |
| `Coloque o dump dentro de scripts\dados_hml\` | O arquivo precisa estar nesta pasta (é a que o container enxerga em `/dados_hml`) |
| `database ... is being accessed by other users` | Algum programa (DBeaver, pgAdmin) está conectado no banco local; feche e repita |
| `Anonimização incompleta` | Nada foi gravado (a transação volta). Mande a mensagem completa para análise |
