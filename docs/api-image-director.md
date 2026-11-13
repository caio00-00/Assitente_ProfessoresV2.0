# API — Relatório do Diretor de Imagem

Documentação das rotas REST expostas em **`/api/v1/image-director`**.

- **Arquivo de implementação:** `app/api/rotas_diretor_imagem.py`
- **Autenticação:** Bearer JWT em todas as rotas (`Authorization: Bearer <token>`)
- **Atualizado em:** 2026-09-04 (branch `hml`)

## Papéis (roles)

| Constante | Papéis |
|-----------|--------|
| `PAPEIS_DIRETOR_IMAGEM` | `admin`, `gestor`, `diretor_chefe`, `diretor_imagem` |
| `PAPEIS_DIRETOR_CHEFE` | `admin`, `gestor`, `diretor_chefe` |

O diretor de imagem (`diretor_imagem`) enxerga e edita **apenas os próprios** relatórios, salvo exceções indicadas abaixo.

---

## Lookups (auto-preenchimento)

| Método | Rota | Papéis | Descrição |
|--------|------|--------|-----------|
| `GET` | `/lookup/diretores` | Diretor imagem+ | Lista diretores selecionáveis. Diretor comum vê só a si; chefe/admin/gestor veem todos. |
| `GET` | `/lookup/turnos-do-dia` | Diretor imagem+ | Turnos/estúdios com aulas do assistente na data (`data`). |
| `GET` | `/lookup/aulas` | Diretor imagem+ | Aulas do Relatório de Aula para `data`, `turno`, `estudio`. |
| `GET` | `/lookup/disciplinas` | Diretor imagem+ | Disciplinas ativas. |
| `GET` | `/lookup/professores` | Diretor imagem+ | Professores ativos. |
| `GET` | `/lookup/professores-por-disciplina/{disciplina_id}` | Diretor imagem+ | Professores vinculados à disciplina. |
| `GET` | `/lookup/existing` | Diretor imagem+ | Relatório IDR existente por diretor+data+turno+estúdio (+ `disciplina_id` opcional). |
| `GET` | `/lookup/users-diretor-imagem` | Diretor chefe+ | Usuários `diretor_imagem` ainda sem cadastro em `DiretorImagem` (admin cadastros). |
| `GET` | `/lookup/checklist-items` | Diretor imagem+ | Itens ativos do checklist de fechamento de estúdio. |
| `GET` | `/lookup/questions` | Diretor imagem+ | Perguntas extras ativas (`nivel` opcional: `por_aula` \| `por_relatorio`). |

### Query params — lookups frequentes

**`GET /lookup/turnos-do-dia`**
- `data` (date, obrigatório)

**`GET /lookup/aulas`**
- `data`, `turno`, `estudio` (obrigatórios)

**`GET /lookup/existing`**
- `data`, `turno`, `estudio` (obrigatórios)
- `disciplina_id` (UUID, opcional)
- `diretor_imagem_id` (UUID, opcional — chefe/admin; diretor usa o próprio)

**`GET /lookup/questions`**
- `nivel` (string, opcional)

---

## Relatório (CRUD e fluxo)

| Método | Rota | Papéis | Descrição |
|--------|------|--------|-----------|
| `POST` | `/` | Diretor imagem+ | Cria relatório (rascunho). Carimba `horario_entrada`. |
| `GET` | `/` | Diretor imagem+ | Listagem paginada do histórico. |
| `GET` | `/{report_id}` | Diretor imagem+ | Detalhe completo (lessons, checklist, respostas extras). |
| `PUT` | `/{report_id}` | Diretor imagem+ | Atualiza cabeçalho (somente `RASCUNHO`). |
| `DELETE` | `/{report_id}` | Diretor chefe+ | Soft delete (`is_deleted=true`). |
| `POST` | `/{report_id}/finalize` | Diretor imagem+ | Finaliza → status `AGUARDANDO_VALIDACAO`. Exige lessons + YouTube. |
| `POST` | `/{report_id}/cancel` | Diretor imagem+ | Cancela relatório (`CANCELADO`). |
| `PATCH` | `/{report_id}/validar` | Diretor chefe+ | Valida (`VALIDADO`). |
| `PATCH` | `/{report_id}/solicitar-correcao` | Diretor chefe+ | Devolve para correção (`RASCUNHO`, `precisa_correcao=true`). Body: `{ observacao_coordenacao }`. |

### Query params — `GET /`

| Param | Tipo | Descrição |
|-------|------|-----------|
| `data_inicio` | date | Filtro data inicial |
| `data_fim` | date | Filtro data final |
| `turma_id` | UUID | Filtro por turma (usado pela grade) |
| `diretor_imagem_id` | UUID | Filtro por diretor (chefe/admin) |
| `estudio` | string | Filtro estúdio |
| `turno` | string | Filtro turno |
| `status` | string | `RASCUNHO`, `AGUARDANDO_VALIDACAO`, `VALIDADO`, `CANCELADO` |
| `precisa_correcao` | bool | Filtro correção pendente |
| `origem` | string | `grade` ou `gravacao_estudio` |
| `limit` | int | Padrão 20, máx. 200 |
| `offset` | int | Paginação |

### Status do relatório

| Status | Significado |
|--------|-------------|
| `RASCUNHO` | Editável |
| `AGUARDANDO_VALIDACAO` | Finalizado, aguardando Diretor-Chefe |
| `VALIDADO` | Aprovado pelo Diretor-Chefe |
| `CANCELADO` | Cancelado |
| `FINALIZADO` | Legado (tratado como validado em PDFs) |

---

## Aulas (blocos técnicos por relatório)

| Método | Rota | Papéis | Descrição |
|--------|------|--------|-----------|
| `POST` | `/{report_id}/lessons` | Diretor imagem+ | Adiciona aula (`AULA 01`, `02`…). Somente rascunho. |
| `PUT` | `/{report_id}/lessons/{lesson_id}` | Diretor imagem+ | Atualiza aula. |
| `DELETE` | `/{report_id}/lessons/{lesson_id}` | Diretor imagem+ | Remove aula e renumera as restantes. |

---

## Checklist e perguntas extras (respostas)

| Método | Rota | Papéis | Descrição |
|--------|------|--------|-----------|
| `PUT` | `/{report_id}/checklist` | Diretor imagem+ | Substitui respostas do checklist de fechamento. Body: `[{ item_id, resposta }]`. |
| `PUT` | `/{report_id}/answers` | Diretor imagem+ | Substitui respostas das perguntas extras (por relatório ou por aula). |

---

## PDF

| Método | Rota | Papéis | Descrição |
|--------|------|--------|-----------|
| `GET` | `/pdf-turno` | Diretor imagem+ | **PDF consolidado do turno** (somente origem `grade`). Inclui relatórios **já finalizados** — parcial permitido. |
| `GET` | `/{report_id}/pdf` | Diretor imagem+ | **PDF individual** de um relatório. |

> **Ordem de registro:** `/pdf-turno` deve ficar **antes** de `/{report_id}` no router (já corrigido) para evitar conflito de path.

### Query params — `GET /pdf-turno`

| Param | Obrigatório | Descrição |
|-------|-------------|-----------|
| `data` | Sim | Data do relatório (`YYYY-MM-DD`) |
| `turno` | Sim | Ex.: `Manhã`, `Tarde` |
| `estudio` | Sim | Ex.: `Estúdio 1` |
| `diretor_imagem_id` | Chefe/admin | Diretor do turno. Diretor comum usa o vínculo automático. |

**Resposta:** `application/pdf` com header `Content-Disposition: attachment`.

**Regras:**
- Ignora relatórios `gravacao_estudio` (PDF avulso separado).
- Ignora rascunhos no PDF; exige ao menos 1 relatório em `AGUARDANDO_VALIDACAO`, `VALIDADO` ou `FINALIZADO`.
- Não exige que **todo** o turno esteja finalizado.

---

## Administração (Diretor-Chefe)

Cadastro de checklist e perguntas extras (telas admin).

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/admin/checklist-items` | Lista todos os itens |
| `POST` | `/admin/checklist-items` | Cria item |
| `PUT` | `/admin/checklist-items/{item_id}` | Atualiza item |
| `DELETE` | `/admin/checklist-items/{item_id}` | Desativa item (`ativo=false`) |
| `GET` | `/admin/questions` | Lista todas as perguntas |
| `POST` | `/admin/questions` | Cria pergunta |
| `PUT` | `/admin/questions/{question_id}` | Atualiza pergunta |
| `DELETE` | `/admin/questions/{question_id}` | Desativa pergunta (`ativa=false`) |

---

## Resumo rápido (todas as rotas)

```
GET    /api/v1/image-director/lookup/diretores
GET    /api/v1/image-director/lookup/turnos-do-dia
GET    /api/v1/image-director/lookup/aulas
GET    /api/v1/image-director/lookup/disciplinas
GET    /api/v1/image-director/lookup/professores
GET    /api/v1/image-director/lookup/professores-por-disciplina/{disciplina_id}
GET    /api/v1/image-director/lookup/existing
GET    /api/v1/image-director/lookup/users-diretor-imagem
GET    /api/v1/image-director/lookup/checklist-items
GET    /api/v1/image-director/lookup/questions

POST   /api/v1/image-director/
GET    /api/v1/image-director/
GET    /api/v1/image-director/pdf-turno
GET    /api/v1/image-director/{report_id}
PUT    /api/v1/image-director/{report_id}
DELETE /api/v1/image-director/{report_id}
POST   /api/v1/image-director/{report_id}/finalize
POST   /api/v1/image-director/{report_id}/cancel
PATCH  /api/v1/image-director/{report_id}/validar
PATCH  /api/v1/image-director/{report_id}/solicitar-correcao

POST   /api/v1/image-director/{report_id}/lessons
PUT    /api/v1/image-director/{report_id}/lessons/{lesson_id}
DELETE /api/v1/image-director/{report_id}/lessons/{lesson_id}

PUT    /api/v1/image-director/{report_id}/checklist
PUT    /api/v1/image-director/{report_id}/answers

GET    /api/v1/image-director/{report_id}/pdf

GET    /api/v1/image-director/admin/checklist-items
POST   /api/v1/image-director/admin/checklist-items
PUT    /api/v1/image-director/admin/checklist-items/{item_id}
DELETE /api/v1/image-director/admin/checklist-items/{item_id}
GET    /api/v1/image-director/admin/questions
POST   /api/v1/image-director/admin/questions
PUT    /api/v1/image-director/admin/questions/{question_id}
DELETE /api/v1/image-director/admin/questions/{question_id}
```

**Total:** 34 rotas.

---

## Rotas novas vs. alteradas (histórico recente)

| Rota | Tipo de mudança |
|------|-----------------|
| `GET /pdf-turno` | **Nova** (v3.3 — PDF consolidado por turno) |
| `GET /lookup/existing` | Resposta tipada (`ExistingReportLookup`) |
| `GET /` | Listagem passou a incluir `youtube_link` e `validado_por_nome` |
| `GET /pdf-turno` | Comportamento: PDF parcial (não exige turno 100% finalizado) |

Demais rotas mantêm **mesma URL e método** desde o fluxo v3.2/v3.3.

---

## Exportação combinada (Auditoria)

Os relatórios do Diretor de Imagem entram na exportação Excel do painel de auditoria:

| Método | Rota | Papéis | Descrição |
|--------|------|--------|-----------|
| `GET` | `/api/v1/reports/export` | Autenticado | Workbook `.xlsx` com 3 abas: **Consolidado**, **Assistente**, **Diretor Imagem** |

- Implementação: `app/services/audit_export.py` (`build_audit_workbook`)
- Filtros: mesmos query params do painel audit (data, turma, professor, disciplina, status, estúdio, pills de atraso/substituição/problema/correção)
- Join assistente ↔ IDR: `class_report_id` + fallback por slot (data, turno, estúdio, turma, disciplina, horário) e YouTube
- Aba **Diretor Imagem**: uma linha por `ImageDirectorLesson`, com colunas dinâmicas de checklist e perguntas extras ativas

Ver também: `data/analises/revisao_exportacao.md`.
