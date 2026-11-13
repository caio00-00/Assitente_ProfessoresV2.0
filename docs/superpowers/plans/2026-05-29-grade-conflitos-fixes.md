# Grade Horária & Conflitos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir 8 bugs críticos de grade horária, choque de horários e integridade de soft-delete no backend FastAPI + PostgreSQL.

**Architecture:** Correções cirúrgicas nos arquivos existentes. Nenhum novo módulo criado. Uma nova migration Alembic para alterar o índice único.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Alembic, pandas.

---

## Files Modified

| File | Change |
|------|--------|
| `app/api/rotas_grade.py:134` | Fix: lê coluna `NOMECLATURA TURMA/TURNO` para `s_nomenclatura` |
| `app/api/rotas_grade.py:162-167` | Add: auto-criação de Turma quando não encontrada |
| `app/models/class_report.py:32-37` | Remove: `UniqueConstraint` do nível Python (será gerido por migration) |
| `app/api/rotas_report.py:199-209` | Fix: gravação usa `or_` em vez de `AND` para estúdio/canal |
| `app/api/rotas_report.py:246-247` | Add: choque de turma (turma overlap) |
| `app/api/rotas_report.py:1374` | Add: `_verificar_choque_horario` no editar_relatorio |
| `app/api/rotas_report.py:612-618` | Fix: captura `IntegrityError` com mensagem amigável |
| `alembic/versions/<new>.py` | New: migration partial unique index |

---

## Task 1: Fix mapeamento de coluna de turma no upload de grade

**File:** `app/api/rotas_grade.py:134`

- [ ] Corrigir `s_nomenclatura` para ler `NOMECLATURA TURMA/TURNO` primeiro
- [ ] Adicionar auto-criação de Turma quando lookup falha
- [ ] Testar `docker compose restart canal_edu_api`

---

## Task 2: Fix lógica de gravação (AND → OR)

**File:** `app/api/rotas_report.py:199-209`

- [ ] Importar `or_` (já importado) e mudar query de gravação para `or_(estudio, canal)`
- [ ] Adicionar choque de turma (turma overlap) na verificação geral

---

## Task 3: Add clash check no editar_relatorio

**File:** `app/api/rotas_report.py:1374`

- [ ] Adicionar `_verificar_choque_horario` antes do `db.commit()` em `editar_relatorio`

---

## Task 4: Fix IntegrityError handling

**File:** `app/api/rotas_report.py`

- [ ] Importar `IntegrityError` de `sqlalchemy.exc`
- [ ] Adicionar catch específico em `criar_relatorio` e `editar_relatorio`

---

## Task 5: Remove UniqueConstraint do modelo Python

**File:** `app/models/class_report.py:32-37`

- [ ] Remover `UniqueConstraint` do `__table_args__` (será gerido pela migration)

---

## Task 6: Nova migration Alembic — partial unique index

**File:** `alembic/versions/<novo>.py`

- [ ] Criar migration que: DROP constraint hard → CREATE partial index WHERE is_deleted = FALSE
- [ ] Executar localmente: `docker exec canal_edu_api alembic upgrade head`

---

## Task 7: Validação de slot da grade (aulas regulares)

**File:** `app/api/rotas_report.py`

- [ ] Adicionar validação opcional: se `regular == "Sim"` e grade tem slot, validar disciplina

---
