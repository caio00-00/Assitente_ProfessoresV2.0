# Canal Educação v4 — o que mudou em relação à v3 (HML)

Base: branch `hml` (commit `806b739`). Esta versão está na pasta
`asssitentes_professores_v4`, branch `refactor/v4`. A pasta do HML não foi tocada.

Cada item diz **antes → agora** e por quê. Os marcados com
**⚠️ MUDA COMPORTAMENTO** são os que alguém vai perceber no uso; confira se
algum deles era intencional na v3 (uma regra específica que parecia sem
sentido mas tinha motivo). Se era, é só avisar que eu volto ao jeito antigo.

Testes: 286 da v3 + 27 novos (`tests/test_v4.py`) = **313 passando**.

---

## Índice

1. [Telas novas e navegação](#1-telas-novas-e-navegação)
2. [Regressões do merge que foram restauradas](#2-regressões-do-merge-que-foram-restauradas)
3. [Dados que se perdiam (e afetam faturamento)](#3-dados-que-se-perdiam-e-afetam-faturamento)
4. [Fluxo dos relatórios: estados e permissões](#4-fluxo-dos-relatórios-estados-e-permissões)
5. [Histórico de versões](#5-histórico-de-versões)
6. [Faturamento e planilha de auditoria](#6-faturamento-e-planilha-de-auditoria)
7. [Busca no Drive e fila do Celery](#7-busca-no-drive-e-fila-do-celery)
8. [Login e segurança](#8-login-e-segurança)
9. [Banco, migrações, Docker e deploy](#9-banco-migrações-docker-e-deploy)
10. [Ajustes técnicos menores](#10-ajustes-técnicos-menores)
11. [O que NÃO foi feito (e por quê)](#11-o-que-não-foi-feito-e-por-quê)
12. [Arquivos novos e alterados](#12-arquivos-novos-e-alterados)

---

## 1. Telas novas e navegação

### Início (`/inicio`) — nova
**Antes:** depois do login, assistentes e coordenação caíam no Dashboard (números gerais) e diretores no Histórico de imagem. Para saber "o que eu preciso fazer", cada pessoa filtrava listas.
**Agora:** todo mundo cai no **Início**, que mostra só o que precisa da ação daquele papel, com um botão para agir em cada item:

| Papel | Grupos que aparecem |
|---|---|
| Assistente | Devolvidos para corrigir (com a nota da coordenação) · Rascunhos · Esperando vídeo e PDF no Drive · Validados |
| Coordenação, admin, gestor, auditor | Prontos para validar · Na fila esperando o Drive · Vermelhos no Drive · Devolvidos ao assistente |
| Diretor de imagem | Devolvidos para corrigir · Vídeo marcado como corrompido · Rascunhos · Aguardando o diretor-chefe |
| Diretor-chefe (e admin/gestor) | Relatórios de imagem para validar · Vídeo corrompido |

Período ajustável (15 a 180 dias). Cada linha mostra se o vídeo e o PDF já chegaram.
API: `GET /api/v1/painel/inicio?dias=45`.

### Linha do tempo da aula (`/aula?cr=<id>` ou `/aula?idr=<id>`) — nova
**Antes:** para entender uma aula era preciso abrir o relatório do assistente, depois o do diretor, depois a auditoria, e deduzir.
**Agora:** uma tela junta a aula de ponta a ponta, em etapas com cor:

1. Relatório do assistente → 2. Relatório do diretor → 3. Os dois conferem (divergências listadas) → 4. Vídeo e PDF no Drive (com o motivo da espera) → 5. Validação da coordenação → 6. Validação do diretor-chefe → 7. Faturamento (lançamento e "cobrar").

Ao lado: os dados dos dois relatórios e o **histórico de versões** de cada um.
Acesso: botão "🧭 Linha do tempo" no Início, no detalhe de Relatórios & Auditoria e na gaveta do Histórico de imagem.
Quem vê: coordenação, admin, gestor, auditor e diretor-chefe veem qualquer aula; assistente só as próprias; diretor de imagem só as dele.
API: `GET /api/v1/aulas/linha-do-tempo?class_report_id=` ou `?image_director_report_id=`.

### Menu
**Antes:** lista única.
**Agora:** "Início" no topo e seções **Aulas / Imagem / Gestão**. As seções só aparecem quando o papel tem algum item nelas. Os itens e as regras de quem vê cada um não mudaram.

### ⚠️ MUDA COMPORTAMENTO — página inicial depois do login
Antes: diretores → `/diretor-imagem/historico`; demais → `/dashboard`. Agora: todos → `/inicio`. Dashboard e Histórico continuam no menu.

---

## 2. Regressões do merge que foram restauradas

O merge `94a77d4` ("Merge branch 'hml' into prd", 01/09/2026) apagou proteções que existiam no commit `919ac31`. Os testes da v3 que cobriam isso estavam falhando.

### ⚠️ MUDA COMPORTAMENTO — choque de horário e arquivo duplicado voltaram
**Antes (HML atual):** sobrou só uma checagem parcial (limite de relatórios por slot da grade). Sumiram: a checagem de **nome de arquivo duplicado**, a comparação de horário em formato único (`07:30 - 08:30` e `07:30 às 08:30` eram tratados como horários diferentes, então a duplicata passava) e a regra de que gravação de estúdio não disputa o slot com a transmissão. Com isso dava para finalizar dois relatórios da mesma aula; o segundo podia "roubar" o vídeo do primeiro na busca do Drive e a aula aparecer duas vezes na planilha. 11 testes da própria v3 sobre isso estavam falhando.
**Agora:** volta a dar erro 409 "⚠️ Choque de horário detectado! Já existe um registro para este slot operacional." e o aviso de nome de arquivo duplicado.
Detalhes que mantive da regra original:
- Rascunhos não bloqueiam ninguém; só relatórios finalizados (aguardando, validado ou o antigo FINALIZADO) contam.
- Gravação de estúdio e transmissão ao vivo não competem pelo mesmo slot.
- A checagem acontece depois do sufixo de aula geminada, então as duas partes de uma geminada não conflitam entre si.
- Ao editar, só conta conflito com outros finalizados.

### Pendências "sem professor" na auditoria
**Antes:** a função que separa pendências com e sem professor vinculado tinha sumido; a tela de Auditoria esperava os campos `pendentes_operacionais` e `pendentes_sem_professor` e mostrava vazio.
**Agora:** restaurada. A estatística volta a separar as duas listas.

---

## 3. Dados que se perdiam (e afetam faturamento)

### Link do PDF apagado ao editar (bug)
**Antes:** o formulário do assistente não envia `slide_link`. Ao salvar uma edição, o backend gravava `slide_link = vazio`, apagando o PDF que a busca do Drive tinha encontrado. A aula voltava para "esperando o Drive" e não podia ser validada.
**Agora:** campos que vêm da busca automática (`slide_link`) não são sobrescritos por uma edição que não os envia. Teste: `test_editar_nao_apaga_pdf_coletado`.

### ⚠️ MUDA COMPORTAMENTO — só coordenação preenche o link do PDF à mão
**Antes:** qualquer um podia mandar `slide_link` na API.
**Agora:** assistentes não definem `slide_link` (o valor é ignorado); coordenação/admin podem. O PDF chega pela busca do Drive.

### ⚠️ MUDA COMPORTAMENTO — cancelar não apaga mais as observações
**Antes:** cancelar gravava a justificativa por cima de `observacoes`; o texto original da aula se perdia.
**Agora:** colunas próprias `justificativa_cancelamento`, `cancelado_por`, `cancelado_em` (relatório de aula e de imagem). `observacoes` fica intacta. A justificativa aparece na linha do tempo.

### ⚠️ MUDA COMPORTAMENTO — excluir
**Antes:** o assistente podia excluir (soft delete) um relatório já finalizado ou validado — ele sumia da planilha de faturamento.
**Agora:** quem não é admin só exclui **rascunho**. Para o resto, use **Cancelar** (fica registrado, com justificativa). Admin continua podendo excluir. Toda exclusão fica no histórico.

### Pedido SEDUC (cobrança dupla) conferido com a Agenda
**Antes:** qualquer relatório podia ser marcado "solicitante = SEDUC", o que dobra a cobrança, sem nenhuma conferência.
**Agora:** quando um assistente marca SEDUC, o sistema exige um agendamento SEDUC na Agenda de Estúdios para a mesma turma (ou sem turma) na data. Sem agendamento → erro 400 explicando. Coordenação e admin podem marcar sem agendamento (casos excepcionais).
> **Confirme:** se na prática a SEDUC pede por outro canal e a Agenda nem sempre é preenchida, isso vai travar o assistente. Dá para desligar e deixar só um aviso.

### Grade com vigência
**Antes:** as checagens de "este horário existe na grade" usavam os slots antigos, ignorando a versão da grade vigente na data.
**Agora:** usam a versão vigente na data da aula (se houver versão ativa); senão, os slots antigos. (`app/services/grade_vigente.py`)

---

## 4. Fluxo dos relatórios: estados e permissões

As regras estavam espalhadas em `if`s em cada rota. Agora estão em dois arquivos:

- `app/domain/estados.py` — o que cada ação faz com cada status.
- `app/domain/politicas.py` — quem pode fazer cada ação.

As mensagens de erro da v3 foram mantidas (ex.: "Assistentes só podem cancelar relatórios criados por eles mesmos.").

### Estados

| Ação | De | Para |
|---|---|---|
| Finalizar | Rascunho, Aguardando, Finalizado (antigo) | Aguardando validação |
| Validar | Aguardando, Finalizado (antigo) | Validado |
| Devolver (pedir correção) | Aguardando, Finalizado, Validado | Rascunho (marcado "devolvido") |
| Reabrir | Validado | Aguardando validação |
| Cancelar | qualquer um, menos Cancelado | Cancelado (final) |

### ⚠️ MUDA COMPORTAMENTO — relatório validado

| | Antes | Agora |
|---|---|---|
| Assistente edita relatório validado | permitido, e continuava "validado" com dados novos não conferidos | **bloqueado (409)**; peça à coordenação para devolver |
| Coordenação edita relatório validado | permitido, continuava validado | permitido, e o relatório **volta para "aguardando validação"** (registrado como REABERTO) |
| Finalizar um validado | voltava para aguardando sem aviso | bloqueado (já está validado) |
| Cancelar um validado | qualquer dono | só coordenação/admin |
| Diretor de imagem edita relatório validado | permitido | bloqueado; o diretor-chefe pode e o relatório reabre |
| Cancelar relatório de imagem validado | qualquer um com acesso | só diretor-chefe/admin/gestor |

Motivo: um relatório validado entra no faturamento. Mudar depois sem nova conferência quebrava a confiança da planilha.

### ⚠️ MUDA COMPORTAMENTO — quem escreve em relatório de aula
**Antes:** o backend já barrava os diretores, mas o **auditor** conseguia criar, editar, finalizar e cancelar relatórios de aula pela API (a tela só escondia os botões).
**Agora:** escrever em relatório de aula exige admin, gestor, coordenador ou assistente. **Auditor fica só leitura.**

### ⚠️ MUDA COMPORTAMENTO — turmas
**Antes:** qualquer usuário logado podia criar, editar, ativar/desativar e clonar turmas pela API.
**Agora:** só admin e gestor (mesmo critério da tela de Cadastros).

### Nome do arquivo ao editar
**Antes:** em relatório finalizado, toda edição recalculava o nome do arquivo; se a regra de nomenclatura tivesse mudado desde a finalização, uma edição qualquer (ex.: corrigir uma observação) trocava o nome e descartava vídeo e PDF já encontrados.
**Agora:** só recalcula se mudar turma, disciplina, data ou conteúdo (ou se ainda não tinha nome). Quando recalcula e o nome muda, continua descartando os links e reiniciando a busca, como antes.

### Finalizar: comparação de "gravação" corrigida
**Antes:** `is_gravacao` comparava com o texto "Gravação", que nunca vinha assim — o valor era sempre falso.
**Agora:** fixado em falso de forma explícita (é o comportamento que de fato rodava). Fica documentado para decidir se a regra deveria existir.

---

## 5. Histórico de versões

**Antes:** só o `audit_logs`, com texto livre; não dava para ver o que um relatório era antes de uma edição.
**Agora:** tabela `report_versions`. Cada evento — CRIADO, EDITADO, FINALIZADO, VALIDADO, DEVOLVIDO, REABERTO, CANCELADO, EXCLUIDO — guarda o status antes/depois, quem, quando, o motivo (nota de devolução, justificativa) e uma **cópia completa** do relatório (inclusive as aulas, no relatório de imagem). Vale para os dois tipos de relatório.

- Relatório de imagem: edições em rascunho não geram versão (seria uma por clique); depois de finalizado, toda mudança em aulas, checklist e respostas gera versão.
- API: `GET /api/v1/historico/{class_report|image_director_report}/{id}?incluir_snapshot=true`.
- Relatórios antigos começam a ter histórico na próxima alteração.

---

## 6. Faturamento e planilha de auditoria

### ⚠️ MUDA COMPORTAMENTO — coluna "COBRAR" respeita o status
**Antes:** a planilha dizia "Sim" para aulas ainda não validadas e até para canceladas.
**Agora:** `cobrar_conforme_status`:
- cancelado → **"Não (cancelado)"**
- falta validar → **"Pendente (falta validar: assistente e diretor)"** (diz qual lado falta)
- os dois validados → o valor da regra de lançamento, como antes.

### Colunas que vinham vazias ou erradas ("campos fantasmas")
O export lia atributos que não existem no modelo e saía vazio sem erro:
- Linhas só com relatório de imagem: data vinha de um campo inexistente → agora `data_relatorio` / `data_referencia`.
- Indicativo de reposição/antecipação → agora vem de `motivo_referencia`.
- "É antecipação" → derivado do lançamento.
- Tipo de cobrança → **DUPLA** se pedido SEDUC, senão **SIMPLES**.
- `VALOR_FATURÁVEL` → deixado em branco de propósito (não há tabela de preços no sistema; antes saía um número sem base).

As mesmas correções nas abas Consolidado e Assistente.

### Não mudou (de propósito)
A regra "COBRAR" de uso de estúdio (`uso_estudio`) ficou igual: a API externa depende dela.

---

## 7. Busca no Drive e fila do Celery

### Tarefas sumindo do Redis
**Antes:** a primeira busca é agendada para 2 h 30 depois de finalizar, mas o Redis devolve tarefas não confirmadas depois de 1 h (padrão). Resultado: tarefas executadas duas vezes ou perdidas.
**Agora:** `visibility_timeout` = 12 h (`CELERY_VISIBILITY_TIMEOUT_SECONDS`), e `worker_prefetch_multiplier = 1`.

### Busca duplicada do mesmo relatório
**Antes:** finalizar, a rotina noturna e o "reprocessar" podiam enfileirar o mesmo relatório várias vezes, em paralelo.
**Agora:** travas no Redis por relatório (`compliance:fila:<id>` e `compliance:rodando:<id>`). Se já está na fila ou rodando, não enfileira de novo. Sem Redis, as travas deixam passar (não travam o sistema).

### A busca para quando o relatório mudou
**Agora** a tarefa desiste se o relatório foi excluído, cancelado ou teve o nome do arquivo alterado desde que foi agendada.

### ⚠️ MUDA COMPORTAMENTO — qual arquivo é escolhido quando há vários
**Antes:** o primeiro que o Drive devolvesse.
**Agora:** prefere o que está nas pastas oficiais (vídeos/PDFs configuradas), depois o maior, depois o mais recente. Não restringe às pastas (há arquivos em subpastas), só dá prioridade. `GOOGLE_DRIVE_RESTRINGIR_PASTAS`.

### Tamanho mínimo do vídeo configurável
**Antes:** 100 MB fixo no código. **Agora:** `COMPLIANCE_MIN_VIDEO_MB` (padrão 100).

### Link vindo de fora (Vimeo / Drive)
- A busca do relatório pelo nome do arquivo usa a nova coluna indexada `nome_normalizado` (antes fazia a normalização linha a linha no Python).
- O link do Drive recebido de fora só é gravado se o relatório não estiver bloqueado para busca (ex.: vídeo corrompido).

### Serviço do Drive
Criado uma vez e reaproveitado (antes, um novo a cada busca).

---

## 8. Login e segurança

### ⚠️ MUDA COMPORTAMENTO
| | Antes | Agora |
|---|---|---|
| E-mail no login | diferenciava maiúsculas | não diferencia |
| Tentativas erradas | ilimitadas | 8 seguidas em 15 min para o mesmo e-mail → 429 "muitas tentativas" (`LOGIN_MAX_ATTEMPTS`, `LOGIN_WINDOW_MINUTES`; 0 desliga) |
| Senha mínima (criar/resetar) | 6 | **8** caracteres |
| Papel no convite | qualquer texto | só os papéis válidos ("coordenadora" vira "coordenador") |
| `/docs` e `/redoc` | abertos | fechados quando `ENVIRONMENT=production` ou `DOCS_ENABLED=false` |
| Erro 500 | mostrava a exceção (às vezes com SQL e dados) | mensagem genérica com um código (`erro a1b2c3d4`) que aparece no log |
| `SECRET_KEY` padrão | aceito em qualquer ambiente | em produção, a API **não sobe** com a chave padrão |
| Forçar reset de senha | o registro no audit log não era salvo | salvo |

Tentativas ficam na tabela nova `login_attempts`.

### Segredos
`docker-compose.yml` não tem mais senhas: tudo vem do `.env` (modelo em `.env.example`). Portas do Postgres e Redis locais ficam só em `127.0.0.1`. O Redis local tem senha.
> **Atenção:** o repositório da v3 tem senhas e chaves em `docker-compose.yml` e em `docs/Oque devemos fazer.md`, no histórico do Git. Trocar essas credenciais (banco de HML, Redis, SMTP, chave JWT) é recomendado mesmo sem subir a v4.

---

## 9. Banco, migrações, Docker e deploy

### Migração nova
`alembic/versions/v4a1b2c3d4e5_v4_historico_cancelamento.py` (depois de `h0i1j2k3l4m5`). Só adiciona — nada é apagado ou renomeado, então a v3 continua funcionando no mesmo banco se precisar voltar:
- colunas de cancelamento nos dois relatórios;
- `class_reports.nome_normalizado` + índice (preenchida para os relatórios existentes);
- tabelas `report_versions` e `login_attempts`.
Pode rodar mais de uma vez sem erro.

### ⚠️ MUDA COMPORTAMENTO — quem cria as tabelas
**Antes:** a cada start, a API rodava `create_all` e um "garantir colunas" na mão, e o Alembic às vezes nem rodava (a URL do banco estava fixa no `env.py`). Um banco vazio não podia ser criado só com Alembic.
**Agora:** `scripts/db_bootstrap.py` roda no start do container (com trava para dois containers não migrarem ao mesmo tempo) e entende três casos:
- banco vazio → cria tudo e marca a versão atual;
- banco antigo sem controle do Alembic → cria o que falta, marca a última versão da v3 e aplica a v4;
- banco já controlado (o HML) → só aplica as migrações novas.
Ao final, preenche o `nome_normalizado` que estiver vazio. `create_all` na subida da API ficou desligado (`AUTO_CREATE_TABLES=false`). O `env.py` do Alembic usa `DATABASE_URL`.

### Docker
- `Dockerfile`: Python 3.11, usuário sem root, `entrypoint.sh` com modos `api` (gunicorn), `api-dev` (reload), `worker`, `beat`.
- **Compatível com o Dokploy atual:** se o Dokploy passar um comando completo (ex.: `uvicorn app.main:app ...`), o entrypoint executa esse comando e roda as migrações antes.
- `docker-compose.yml`: local completo (Postgres, Redis, API, worker, beat). `docker-compose.supabase.yml`: sem Postgres, usando o Supabase.
- `.dockerignore` deixa fora da imagem os scripts de análise da raiz e os dumps.
- O entrypoint é copiado para fora de `/app` na imagem, então um compose que monta o código em `/app` (como o antigo `.:/app`) não o substitui, e um checkout do Windows com CRLF não quebra. `.gitattributes` força LF nos `.sh`.

### O que ficou igual no compose, de propósito (para o Dokploy)
Mesmos nomes de serviço, **mesmo volume do banco (`postgres_data_final`)**, mesmo usuário e mesmo nome de banco padrão (`postgres-prd`). Trocar o volume faria o Postgres subir vazio no servidor.
### ⚠️ MUDA COMPORTAMENTO — o que mudou no compose
Senhas saem do arquivo e vêm do ambiente; Postgres e Redis escutam só em `127.0.0.1` (antes, em todas as interfaces); o Redis passa a ter senha. Detalhes em `DEPLOY_DOKPLOY.md`.

### Dados de HML no local
`scripts/dados_hml/` — exporta no servidor, importa no Docker local e anonimiza nomes, e-mails e senhas. Guia: `scripts/dados_hml/DADOS_HML.md`.

---

## 10. Ajustes técnicos menores

- WebSocket da auditoria: o aviso de "relatório atualizado" era disparado de uma thread sem loop e falhava calado; agora usa `anyio.from_thread`.
- `pypdf` 7: o PDF com papel timbrado do diretor de imagem quebrava (`merge` em página solta); ordem corrigida.
- `requirements.txt` com limites de versão (evita uma atualização quebrar o build do Dokploy).
- Nome do arquivo na Auditoria passa por `escapeHtml`.
- Celery lê o `REDIS_URL` das configurações da aplicação (o mesmo do `.env`, com senha).

---

## 11. O que NÃO foi feito (e por quê)

| Item | Situação |
|---|---|
| Login para as páginas (servidor) | As páginas HTML não checam login no servidor; quem barra é o JavaScript e a API (os dados não vazam, a página vazia abre). Resolver exige cookie de sessão — mudança grande, fica para a próxima etapa. |
| Live Monitor sem login | Mesmo caso acima. |
| Dividir `rotas_report.py` (3 mil linhas) em módulos | Arriscado junto com tantas mudanças de regra. As regras já saíram para `domain/`; a divisão pode vir depois, sem mudar comportamento. |
| Catálogo de disciplinas/nomenclatura no banco com versão | Precisa definir com a coordenação como versionar a nomenclatura. |
| Tabela própria ligando aula ↔ relatório de imagem | Hoje o par é achado por vínculo direto, grade ou YouTube. A linha do tempo mostra qual foi usado; a tabela própria fica para depois. |
| "COBRAR" do uso de estúdio | Mantido igual por causa da API externa. |
| Valor faturável | Não há tabela de preços no sistema. |
| Vercel | Fora do escopo (combinado: Docker local + Supabase). |

---

## 12. Arquivos novos e alterados

**Novos**
- `app/domain/politicas.py`, `app/domain/estados.py` — regras de permissão e de status
- `app/models/historico.py` — `ReportVersion`, `LoginAttempt`
- `app/services/historico.py`, `grade_vigente.py`, `fila_compliance.py`
- `app/api/rotas_v4.py` — Início, linha do tempo, histórico
- `app/templates/inicio.html`, `aula.html`
- `alembic/versions/v4a1b2c3d4e5_v4_historico_cancelamento.py`
- `scripts/db_bootstrap.py`, `scripts/dados_hml/*`
- `docker-compose.supabase.yml`, `.env.example`, `entrypoint.sh`
- `tests/test_v4.py`
- `docs/v4/*`

**Alterados (principais)**
- `app/api/rotas_report.py` — estados, permissões, histórico, duplicidade restaurada, slide_link, SEDUC, exclusão, cancelamento, auditoria
- `app/api/rotas_diretor_imagem.py` — validado, cancelamento, histórico
- `app/api/rotas_auth.py`, `app/schemas/auth.py` — login, senha, convite
- `app/api/rotas_turma.py` — permissões
- `app/api/rotas_externas.py` — Vimeo/Drive
- `app/services/audit_export.py` — COBRAR e campos fantasmas
- `app/services/sync_drive.py`, `app/tasks/worker.py`, `app/core/celery_app.py` — Drive e fila
- `app/core/config.py`, `app/main.py`, `alembic/env.py`
- `app/models/class_report.py`, `image_director_report.py`
- `app/templates/base.html`, `login.html`, `reports_audit.html`, `image_director_reports_list.html`, `app/static/js/app.js`, `app/static/css/style.css`
- `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.gitignore`, `.dockerignore`

---

## 13. v4.1 — rodar também na Vercel + Supabase

O mesmo código roda no Docker/Dokploy (como antes) e na Vercel (sem Docker). Guia: `DEPLOY_VERCEL.md`.

- **Detecção automática:** na Vercel (`VERCEL=1`) o sistema usa `MODO_TAREFAS=direto`, banco sem pool (`NullPool`, quem segura as conexões é o pooler do Supabase) e desliga o WebSocket. No Docker nada muda.
- **Busca no Drive sem worker:** o miolo da tarefa do Celery virou `verificar_uma_vez` (`app/tasks/worker.py`). O Celery continua usando, com as mesmas tentativas. Sem worker, `app/services/tarefas.py` roda a busca na própria API:
  - **Buscar no Drive** faz a varredura na hora e mostra o resultado;
  - **Reverificar** busca aquele relatório na hora;
  - o cron chama `/api/v1/sistema/varredura`.
- **⚠️ MUDA COMPORTAMENTO (só sem worker):** depois de finalizar, a busca não é agendada; ela roda na varredura seguinte, que respeita o mesmo atraso inicial de 2 h 30. O Vermelho é marcado quando o relatório passa do tempo que as tentativas do worker levariam.
- **Coluna nova** `class_reports.compliance_verificado_em` (migração `v4b2c3d4e5f6`, só adiciona): guarda quando a busca olhou o relatório pela última vez. A varredura começa pelos que estão há mais tempo sem olhar.
- **Rotas novas** em `/api/v1/sistema/` (`app/api/rotas_sistema.py`):
  - `saude` é pública;
  - `varredura` e `migrar` exigem `Authorization: Bearer <CRON_SECRET>` e ficam desligadas sem `CRON_SECRET`;
  - `migrar` cria o primeiro admin se o banco não tiver usuários.
- **E-mails:** sem worker são enviados na hora.
- **Arquivos novos:** `index.py`, `vercel.json` (cron diário), `.vercelignore`, `.python-version`, `tests/test_v41_vercel.py` (12 testes).
