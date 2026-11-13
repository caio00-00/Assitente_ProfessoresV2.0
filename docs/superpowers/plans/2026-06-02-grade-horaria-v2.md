# Grade Horária v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o fluxo de upload de planilha por um sistema de infraestrutura configurável (estudios, canais IPTV, slots de horário) e versionamento de grade por turma, com verificação global de choque de horários.

**Architecture:** Duas camadas — infraestrutura (Configurações: Estudio, CanalIptvModel, SlotHorario) como pré-requisito, e grade da turma (GradeVersao + slots) com choque global entre grades ativas. O `POST /turmas` passa a exigir ao menos um slot de grade. A tabela `grade` existente recebe colunas novas (grade_versao_id, estudio_id, canal_iptv_id, slot_horario_id, tipo_slot) e o campo `dia_semana` migra de String para Integer.

**Tech Stack:** Python 3.11, FastAPI 0.109, SQLAlchemy 2.0, PostgreSQL 15, Alembic 1.13, Jinja2, JavaScript vanilla.

---

## Scope Map — Arquivos afetados

| Ação | Arquivo |
|---|---|
| CREATE | `app/models/infraestrutura.py` |
| MODIFY | `app/models/auxiliares.py` |
| MODIFY | `app/models/__init__.py` |
| CREATE | `alembic/versions/XXXX_grade_horaria_v2.py` |
| MODIFY | `alembic/env.py` |
| CREATE | `app/api/rotas_configuracoes.py` |
| CREATE | `app/api/rotas_grade_versao.py` |
| MODIFY | `app/api/rotas_turma.py` |
| MODIFY | `app/api/rotas_live.py` |
| MODIFY | `app/main.py` |
| DELETE | `app/api/rotas_grade.py` |
| MODIFY | `app/templates/admin_cadastros.html` |
| MODIFY | `app/templates/grade.html` |

---

## Task 1: Criar os novos modelos SQLAlchemy

**Files:**
- Create: `app/models/infraestrutura.py`
- Modify: `app/models/auxiliares.py` (atualizar Grade, remover GradeRascunho)
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Criar `app/models/infraestrutura.py`**

```python
"""
Canal Educação v3.0 — Modelos de Infraestrutura (Grade Horária v2).
Estudio, CanalIptvModel, SlotHorario, GradeVersao.
"""

from datetime import datetime
from sqlalchemy import (
    Boolean, Column, Integer, String, Time, Timestamp, ForeignKey, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Estudio(Base):
    __tablename__ = "estudio"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False)
    horario_inicio = Column(Time, nullable=False)
    horario_fim = Column(Time, nullable=False)
    funciona_24h = Column(Boolean, nullable=False, default=False)
    ativo = Column(Boolean, nullable=False, default=True)
    data_criacao = Column(Timestamp, nullable=False, default=datetime.utcnow)


class CanalIptvModel(Base):
    __tablename__ = "canal_iptv"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False)
    numero = Column(Integer, nullable=False, unique=True)
    ativo = Column(Boolean, nullable=False, default=True)
    data_criacao = Column(Timestamp, nullable=False, default=datetime.utcnow)


class SlotHorario(Base):
    __tablename__ = "slot_horario"

    id = Column(Integer, primary_key=True, autoincrement=True)
    turno = Column(String(20), nullable=False)
    ordem = Column(Integer, nullable=False)
    horario_inicio = Column(Time, nullable=False)
    horario_fim = Column(Time, nullable=False)
    ativo = Column(Boolean, nullable=False, default=True)
    data_criacao = Column(Timestamp, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("turno IN ('manha','tarde','noite','madrugada')", name="chk_turno"),
        CheckConstraint("horario_fim > horario_inicio", name="chk_horario"),
    )


class GradeVersao(Base):
    __tablename__ = "grade_versao"

    id = Column(Integer, primary_key=True, autoincrement=True)
    turma_id = Column(UUID(as_uuid=True), ForeignKey("turmas.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    data_ativacao = Column(Timestamp, nullable=True)
    data_criacao = Column(Timestamp, nullable=False, default=datetime.utcnow)
    criado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    turma = relationship("Turma", backref="grade_versoes")
    slots = relationship("Grade", back_populates="grade_versao")
```

- [ ] **Step 2: Atualizar `app/models/auxiliares.py` — atualizar `Grade`, remover `GradeRascunho`**

Substituir todo o conteúdo do arquivo pelo seguinte (preservando Unit, Professor, Disciplina, ProfessorDisciplina sem alteração; atualizando Grade; removendo GradeRascunho):

```python
"""
Canal Educação v3.0 — Modelos Auxiliares / Fundação.
Tabelas base: Unit, Professor, Disciplina, Grade, ProfessorDisciplina (M:N).
"""

import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Time, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Unit(Base):
    __tablename__ = "units"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(255), nullable=False)

    turmas = relationship("Turma", back_populates="unit")


class ProfessorDisciplina(Base):
    """Tabela associativa M:N entre Professor e Disciplina."""

    __tablename__ = "professor_disciplinas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    professor_id = Column(
        UUID(as_uuid=True), ForeignKey("professores.id"), nullable=False
    )
    disciplina_id = Column(
        UUID(as_uuid=True), ForeignKey("disciplinas.id"), nullable=False
    )


class Professor(Base):
    __tablename__ = "professores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)

    disciplinas = relationship(
        "Disciplina",
        secondary="professor_disciplinas",
        back_populates="professores",
    )


class Disciplina(Base):
    __tablename__ = "disciplinas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(255), nullable=False)
    nomenclatura_padrao = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    professores = relationship(
        "Professor",
        secondary="professor_disciplinas",
        back_populates="disciplinas",
    )


class Grade(Base):
    __tablename__ = "grades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # --- Relacionamentos principais ---
    turma_id = Column(UUID(as_uuid=True), ForeignKey("turmas.id"), nullable=True)
    disciplina_id = Column(UUID(as_uuid=True), ForeignKey("disciplinas.id"), nullable=True)
    professor_id = Column(UUID(as_uuid=True), ForeignKey("professores.id"), nullable=True)

    # --- Novos FKs (Grade v2) ---
    grade_versao_id = Column(Integer, ForeignKey("grade_versao.id"), nullable=True)
    slot_horario_id = Column(Integer, ForeignKey("slot_horario.id"), nullable=True)
    estudio_id = Column(Integer, ForeignKey("estudio.id"), nullable=True)
    canal_iptv_id = Column(Integer, ForeignKey("canal_iptv.id"), nullable=True)
    tipo_slot = Column(String(20), nullable=False, default="aula")  # 'aula' | 'gravacao'

    # --- Horários ---
    dia_semana = Column(Integer, nullable=False, default=0)  # 0=Segunda … 6=Domingo
    horario_inicio = Column(Time, nullable=False)
    horario_fim = Column(Time, nullable=False)
    turno_aula = Column(String(20), nullable=True)  # mantido por compat. legado

    # --- Legado (mantidos para não quebrar código existente) ---
    canal_iptv = Column(Integer, nullable=True)  # número direto legado
    descricao = Column(String(255), nullable=True)
    vigencia_inicio = Column(Date, nullable=True)
    vigencia_fim = Column(Date, nullable=True)
    versao = Column(String(50), nullable=True)

    # --- Relationships ---
    turma = relationship("Turma", backref="grades")
    disciplina = relationship("Disciplina", backref="grades")
    professor = relationship("Professor", backref="grades")
    grade_versao = relationship("GradeVersao", back_populates="slots")
    estudio = relationship("Estudio")
    canal_iptv_obj = relationship("CanalIptvModel")
    slot_horario = relationship("SlotHorario")
```

- [ ] **Step 3: Atualizar `app/models/__init__.py`**

```python
"""
Canal Educação v3.0 — Models package init.
"""

from app.models.audit_log import AuditLog
from app.models.auxiliares import (
    Disciplina,
    Grade,
    Professor,
    ProfessorDisciplina,
    Unit,
)
from app.models.class_report import ClassReport
from app.models.infraestrutura import Estudio, CanalIptvModel, SlotHorario, GradeVersao
from app.models.turma import Turma
from app.models.user import User
from app.models.diretor_imagem import DiretorImagem

__all__ = [
    "AuditLog",
    "User",
    "Turma",
    "ClassReport",
    "Professor",
    "Disciplina",
    "Grade",
    "Unit",
    "ProfessorDisciplina",
    "DiretorImagem",
    "Estudio",
    "CanalIptvModel",
    "SlotHorario",
    "GradeVersao",
]
```

- [ ] **Step 4: Verificar que os modelos importam sem erro**

```bash
docker compose exec api python -c "from app.models import Estudio, CanalIptvModel, SlotHorario, GradeVersao, Grade; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add app/models/infraestrutura.py app/models/auxiliares.py app/models/__init__.py
git commit -m "feat: adiciona modelos de infraestrutura e atualiza Grade para v2"
```

---

## Task 2: Criar a migration Alembic

**Files:**
- Create: `alembic/versions/XXXX_grade_horaria_v2.py` (nome gerado pelo Alembic)
- Modify: `alembic/env.py`

- [ ] **Step 1: Atualizar `alembic/env.py` para importar novos modelos**

Localizar linha 15:
```python
from app.models import user, turma, class_report
```

Substituir por:
```python
from app.models import user, turma, class_report, infraestrutura
from app.models.auxiliares import Grade, Unit, Professor, Disciplina, ProfessorDisciplina
```

- [ ] **Step 2: Gerar o arquivo de migration**

```bash
docker compose exec api alembic revision --autogenerate -m "grade_horaria_v2"
```

Expected: arquivo criado em `alembic/versions/XXXX_grade_horaria_v2.py`

- [ ] **Step 3: Editar a migration gerada para incluir a conversão de dia_semana e o seed inicial**

O Alembic vai gerar as tabelas novas e as colunas novas, mas NÃO vai gerar a conversão do tipo de `dia_semana`. Substituir o corpo `upgrade()` pelo seguinte (adaptando o `revision` e `down_revision` gerados automaticamente — NÃO alterar esses campos):

```python
def upgrade() -> None:
    # 1. Criar tabelas de infraestrutura
    op.create_table(
        "estudio",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(100), nullable=False),
        sa.Column("horario_inicio", sa.Time(), nullable=False),
        sa.Column("horario_fim", sa.Time(), nullable=False),
        sa.Column("funciona_24h", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("data_criacao", sa.TIMESTAMP(), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "canal_iptv",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(100), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("data_criacao", sa.TIMESTAMP(), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("numero"),
    )
    op.create_table(
        "slot_horario",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("turno", sa.String(20), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("horario_inicio", sa.Time(), nullable=False),
        sa.Column("horario_fim", sa.Time(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("data_criacao", sa.TIMESTAMP(), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("turno IN ('manha','tarde','noite','madrugada')", name="chk_turno"),
        sa.CheckConstraint("horario_fim > horario_inicio", name="chk_horario"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "grade_versao",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("turma_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("data_ativacao", sa.TIMESTAMP(), nullable=True),
        sa.Column("data_criacao", sa.TIMESTAMP(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("criado_por", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["turma_id"], ["turmas.id"]),
        sa.ForeignKeyConstraint(["criado_por"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. Adicionar colunas novas à tabela grade
    op.add_column("grades", sa.Column("grade_versao_id", sa.Integer(), sa.ForeignKey("grade_versao.id"), nullable=True))
    op.add_column("grades", sa.Column("slot_horario_id", sa.Integer(), sa.ForeignKey("slot_horario.id"), nullable=True))
    op.add_column("grades", sa.Column("estudio_id", sa.Integer(), sa.ForeignKey("estudio.id"), nullable=True))
    op.add_column("grades", sa.Column("canal_iptv_id", sa.Integer(), sa.ForeignKey("canal_iptv.id"), nullable=True))
    op.add_column("grades", sa.Column("tipo_slot", sa.String(20), nullable=False, server_default="aula"))

    # 3. Migrar dia_semana de String para Integer
    #    Primeiro: adicionar coluna temporária
    op.add_column("grades", sa.Column("dia_semana_int", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE grades SET dia_semana_int = CASE
            WHEN UPPER(dia_semana::text) IN ('SEGUNDA','SEG','MONDAY') THEN 0
            WHEN UPPER(dia_semana::text) IN ('TERÇA','TERCA','TER','TUESDAY') THEN 1
            WHEN UPPER(dia_semana::text) IN ('QUARTA','QUA','WEDNESDAY') THEN 2
            WHEN UPPER(dia_semana::text) IN ('QUINTA','QUI','THURSDAY') THEN 3
            WHEN UPPER(dia_semana::text) IN ('SEXTA','SEX','FRIDAY') THEN 4
            WHEN UPPER(dia_semana::text) IN ('SÁBADO','SABADO','SAB','SATURDAY') THEN 5
            WHEN UPPER(dia_semana::text) IN ('DOMINGO','DOM','SUNDAY') THEN 6
            ELSE 0
        END
    """)
    #    Segundo: dropar coluna antiga e renomear
    op.drop_column("grades", "dia_semana")
    op.alter_column("grades", "dia_semana_int", new_column_name="dia_semana", nullable=False, server_default="0")

    # 4. Seed: criar GradeVersao ativa para cada turma que já tem grades
    op.execute("""
        INSERT INTO grade_versao (turma_id, is_active, data_ativacao, data_criacao)
        SELECT DISTINCT turma_id, true, NOW(), NOW()
        FROM grades
        WHERE turma_id IS NOT NULL
    """)
    # Vincular grades existentes à versão ativa recém-criada
    op.execute("""
        UPDATE grades g
        SET grade_versao_id = gv.id
        FROM grade_versao gv
        WHERE gv.turma_id = g.turma_id
          AND gv.is_active = true
          AND g.grade_versao_id IS NULL
    """)


def downgrade() -> None:
    # Reverter dia_semana de int para string (aproximado)
    op.add_column("grades", sa.Column("dia_semana_str", sa.String(20), nullable=True))
    op.execute("""
        UPDATE grades SET dia_semana_str = CASE dia_semana
            WHEN 0 THEN 'SEGUNDA' WHEN 1 THEN 'TERÇA' WHEN 2 THEN 'QUARTA'
            WHEN 3 THEN 'QUINTA' WHEN 4 THEN 'SEXTA' WHEN 5 THEN 'SÁBADO'
            WHEN 6 THEN 'DOMINGO' ELSE 'SEGUNDA'
        END
    """)
    op.drop_column("grades", "dia_semana")
    op.alter_column("grades", "dia_semana_str", new_column_name="dia_semana")
    op.drop_column("grades", "tipo_slot")
    op.drop_column("grades", "canal_iptv_id")
    op.drop_column("grades", "estudio_id")
    op.drop_column("grades", "slot_horario_id")
    op.drop_column("grades", "grade_versao_id")
    op.drop_table("grade_versao")
    op.drop_table("slot_horario")
    op.drop_table("canal_iptv")
    op.drop_table("estudio")
```

**Também adicionar ao início do arquivo de migration os imports necessários:**
```python
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
```

- [ ] **Step 4: Aplicar a migration**

```bash
docker compose exec api alembic upgrade head
```

Expected: sem erros, migration aplicada com sucesso.

- [ ] **Step 5: Verificar tabelas criadas**

```bash
docker compose exec db psql -U assistente_professores postgres-prd -c "\dt"
```

Expected: listar `estudio`, `canal_iptv`, `slot_horario`, `grade_versao` entre as tabelas.

- [ ] **Step 6: Verificar conversão dia_semana**

```bash
docker compose exec db psql -U assistente_professores postgres-prd -c "SELECT dia_semana, count(*) FROM grades GROUP BY dia_semana ORDER BY dia_semana;"
```

Expected: valores 0-6 ao invés de strings.

- [ ] **Step 7: Commit**

```bash
git add alembic/ 
git commit -m "feat: migration grade_horaria_v2 - novas tabelas + dia_semana int + seed GradeVersao"
```

---

## Task 3: Endpoints de Infraestrutura (Configurações)

**Files:**
- Create: `app/api/rotas_configuracoes.py`

- [ ] **Step 1: Criar `app/api/rotas_configuracoes.py`**

```python
"""
Canal Educação v3.0 — Rotas de Configuração de Infraestrutura (Grade v2).
CRUD para Estudio, CanalIptvModel, SlotHorario.
"""

from datetime import time as time_type
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.database import get_db
from app.models.infraestrutura import Estudio, CanalIptvModel, SlotHorario
from app.models.user import User

router = APIRouter(prefix="/api/v1/configuracoes", tags=["Configurações de Infraestrutura"])

# ── Turnos válidos e faixas de horário ────────────────────────────────

TURNO_FAIXAS = {
    "manha":     (time_type(5, 0),  time_type(12, 0)),
    "tarde":     (time_type(12, 0), time_type(18, 0)),
    "noite":     (time_type(18, 0), time_type(23, 59)),
    "madrugada": (time_type(0, 0),  time_type(5, 0)),
}


def _parse_time(t_str: str) -> time_type:
    try:
        h, m = t_str.split(":")
        return time_type(int(h), int(m))
    except Exception:
        raise ValueError(f"Horário inválido: '{t_str}'. Use HH:MM.")


def _slot_turno_valido(turno: str, inicio: time_type) -> bool:
    faixa = TURNO_FAIXAS.get(turno)
    if not faixa:
        return False
    inicio_faixa, fim_faixa = faixa
    if turno == "madrugada":
        return inicio >= inicio_faixa or inicio < fim_faixa
    return inicio_faixa <= inicio < fim_faixa


# ── Schemas ───────────────────────────────────────────────────────────

class EstudioIn(BaseModel):
    nome: str
    horario_inicio: str   # "HH:MM"
    horario_fim: str      # "HH:MM"
    funciona_24h: bool = False


class EstudioOut(BaseModel):
    id: int
    nome: str
    horario_inicio: Optional[str]
    horario_fim: Optional[str]
    funciona_24h: bool
    ativo: bool

    class Config:
        from_attributes = True


class CanalIn(BaseModel):
    nome: str
    numero: int


class CanalOut(BaseModel):
    id: int
    nome: str
    numero: int
    ativo: bool

    class Config:
        from_attributes = True


class SlotIn(BaseModel):
    turno: str
    ordem: int
    horario_inicio: str  # "HH:MM"
    horario_fim: str     # "HH:MM"


class SlotOut(BaseModel):
    id: int
    turno: str
    ordem: int
    horario_inicio: Optional[str]
    horario_fim: Optional[str]
    ativo: bool

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────

def _fmt_time(t) -> Optional[str]:
    return t.strftime("%H:%M") if t else None


def _estudio_out(e: Estudio) -> dict:
    return {
        "id": e.id, "nome": e.nome,
        "horario_inicio": _fmt_time(e.horario_inicio),
        "horario_fim": _fmt_time(e.horario_fim),
        "funciona_24h": e.funciona_24h, "ativo": e.ativo,
    }


def _slot_out(s: SlotHorario) -> dict:
    return {
        "id": s.id, "turno": s.turno, "ordem": s.ordem,
        "horario_inicio": _fmt_time(s.horario_inicio),
        "horario_fim": _fmt_time(s.horario_fim), "ativo": s.ativo,
    }


# ── Estúdios ──────────────────────────────────────────────────────────

@router.get("/estudios")
def listar_estudios(db: Session = Depends(get_db),
                    current_user: User = Depends(require_role("admin", "gestor"))):
    return [_estudio_out(e) for e in db.query(Estudio).order_by(Estudio.id).all()]


@router.post("/estudios", status_code=201)
def criar_estudio(data: EstudioIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_role("admin", "gestor"))):
    h_ini = _parse_time(data.horario_inicio)
    h_fim = _parse_time(data.horario_fim)
    e = Estudio(nome=data.nome, horario_inicio=h_ini, horario_fim=h_fim, funciona_24h=data.funciona_24h)
    db.add(e)
    db.commit()
    db.refresh(e)
    return _estudio_out(e)


@router.patch("/estudios/{id}")
def editar_estudio(id: int, data: EstudioIn, db: Session = Depends(get_db),
                   current_user: User = Depends(require_role("admin", "gestor"))):
    e = db.query(Estudio).filter(Estudio.id == id).first()
    if not e:
        raise HTTPException(404, "Estúdio não encontrado.")
    e.nome = data.nome
    e.horario_inicio = _parse_time(data.horario_inicio)
    e.horario_fim = _parse_time(data.horario_fim)
    e.funciona_24h = data.funciona_24h
    db.commit()
    db.refresh(e)
    return _estudio_out(e)


@router.delete("/estudios/{id}", status_code=204)
def desativar_estudio(id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(require_role("admin", "gestor"))):
    e = db.query(Estudio).filter(Estudio.id == id).first()
    if not e:
        raise HTTPException(404, "Estúdio não encontrado.")
    e.ativo = False
    db.commit()


# ── Canais IPTV ───────────────────────────────────────────────────────

@router.get("/canais-iptv")
def listar_canais(db: Session = Depends(get_db),
                  current_user: User = Depends(require_role("admin", "gestor"))):
    return db.query(CanalIptvModel).order_by(CanalIptvModel.numero).all()


@router.post("/canais-iptv", status_code=201)
def criar_canal(data: CanalIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_role("admin", "gestor"))):
    if db.query(CanalIptvModel).filter(CanalIptvModel.numero == data.numero).first():
        raise HTTPException(409, f"Canal número {data.numero} já existe.")
    c = CanalIptvModel(nome=data.nome, numero=data.numero)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.patch("/canais-iptv/{id}")
def editar_canal(id: int, data: CanalIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_role("admin", "gestor"))):
    c = db.query(CanalIptvModel).filter(CanalIptvModel.id == id).first()
    if not c:
        raise HTTPException(404, "Canal não encontrado.")
    conflito = db.query(CanalIptvModel).filter(CanalIptvModel.numero == data.numero, CanalIptvModel.id != id).first()
    if conflito:
        raise HTTPException(409, f"Canal número {data.numero} já existe.")
    c.nome = data.nome
    c.numero = data.numero
    db.commit()
    db.refresh(c)
    return c


@router.delete("/canais-iptv/{id}", status_code=204)
def desativar_canal(id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(require_role("admin", "gestor"))):
    c = db.query(CanalIptvModel).filter(CanalIptvModel.id == id).first()
    if not c:
        raise HTTPException(404, "Canal não encontrado.")
    c.ativo = False
    db.commit()


# ── Slots de Horário ──────────────────────────────────────────────────

@router.get("/slots-horario")
def listar_slots(turno: Optional[str] = None, db: Session = Depends(get_db),
                 current_user: User = Depends(require_role("admin", "gestor"))):
    q = db.query(SlotHorario)
    if turno:
        q = q.filter(SlotHorario.turno == turno.lower())
    return [_slot_out(s) for s in q.order_by(SlotHorario.turno, SlotHorario.ordem).all()]


@router.post("/slots-horario", status_code=201)
def criar_slot(data: SlotIn, db: Session = Depends(get_db),
               current_user: User = Depends(require_role("admin", "gestor"))):
    turno = data.turno.lower()
    if turno not in TURNO_FAIXAS:
        raise HTTPException(422, f"Turno inválido. Use: {list(TURNO_FAIXAS.keys())}")
    h_ini = _parse_time(data.horario_inicio)
    h_fim = _parse_time(data.horario_fim)
    if not _slot_turno_valido(turno, h_ini):
        raise HTTPException(422, f"horario_inicio '{data.horario_inicio}' não pertence ao turno '{turno}'.")
    s = SlotHorario(turno=turno, ordem=data.ordem, horario_inicio=h_ini, horario_fim=h_fim)
    db.add(s)
    db.commit()
    db.refresh(s)
    return _slot_out(s)


@router.patch("/slots-horario/{id}")
def editar_slot(id: int, data: SlotIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_role("admin", "gestor"))):
    s = db.query(SlotHorario).filter(SlotHorario.id == id).first()
    if not s:
        raise HTTPException(404, "Slot não encontrado.")
    turno = data.turno.lower()
    h_ini = _parse_time(data.horario_inicio)
    h_fim = _parse_time(data.horario_fim)
    if not _slot_turno_valido(turno, h_ini):
        raise HTTPException(422, f"horario_inicio '{data.horario_inicio}' não pertence ao turno '{turno}'.")
    s.turno = turno
    s.ordem = data.ordem
    s.horario_inicio = h_ini
    s.horario_fim = h_fim
    db.commit()
    db.refresh(s)
    return _slot_out(s)


@router.delete("/slots-horario/{id}", status_code=204)
def desativar_slot(id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(require_role("admin", "gestor"))):
    s = db.query(SlotHorario).filter(SlotHorario.id == id).first()
    if not s:
        raise HTTPException(404, "Slot não encontrado.")
    s.ativo = False
    db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add app/api/rotas_configuracoes.py
git commit -m "feat: endpoints CRUD de infraestrutura - estudios, canais IPTV, slots de horário"
```

---

## Task 4: Endpoints de Grade Versão + Verificar Choque

**Files:**
- Create: `app/api/rotas_grade_versao.py`

- [ ] **Step 1: Criar `app/api/rotas_grade_versao.py`**

```python
"""
Canal Educação v3.0 — Endpoints de Versionamento de Grade (v2).
GradeVersao CRUD, slots, ativação e verificação de choque global.
"""

from datetime import datetime, time as time_type
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_role
from app.core.database import get_db
from app.models.auxiliares import Grade, Disciplina
from app.models.infraestrutura import GradeVersao, Estudio, CanalIptvModel, SlotHorario
from app.models.turma import Turma
from app.models.user import User

router = APIRouter(tags=["Grade Versão"])


# ─── Schemas ──────────────────────────────────────────────────────────

class SlotCreateIn(BaseModel):
    slot_horario_id: Optional[int] = None
    dia_semana: int                          # 0=Segunda…6=Domingo
    disciplina_id: UUID
    estudio_id: int
    canal_iptv_id: int
    tipo_slot: str = "aula"                  # 'aula' | 'gravacao'
    # Para gravação (horário livre):
    horario_inicio: Optional[str] = None     # "HH:MM"
    horario_fim: Optional[str] = None        # "HH:MM"


class ChoqueCheckIn(BaseModel):
    dia_semana: int
    horario_inicio: str   # "HH:MM"
    horario_fim: str      # "HH:MM"
    estudio_id: int
    canal_iptv_id: int
    grade_versao_id_excluir: Optional[int] = None


# ─── Helpers ──────────────────────────────────────────────────────────

def _parse_time(t_str: str) -> time_type:
    try:
        h, m = t_str.split(":")
        return time_type(int(h), int(m))
    except Exception:
        raise ValueError(f"Horário inválido: '{t_str}'")


def _verificar_choque(
    db: Session,
    dia_semana: int,
    horario_inicio: time_type,
    horario_fim: time_type,
    estudio_id: int,
    canal_iptv_id: int,
    grade_versao_id_excluir: Optional[int] = None,
) -> Optional[dict]:
    """Retorna detalhes do primeiro slot conflitante, ou None."""
    q = (
        db.query(Grade, GradeVersao, Turma, Disciplina)
        .join(GradeVersao, Grade.grade_versao_id == GradeVersao.id)
        .join(Turma, GradeVersao.turma_id == Turma.id)
        .join(Disciplina, Grade.disciplina_id == Disciplina.id)
        .filter(
            GradeVersao.is_active == True,
            Grade.dia_semana == dia_semana,
            Grade.horario_inicio < horario_fim,
            Grade.horario_fim > horario_inicio,
            or_(
                Grade.estudio_id == estudio_id,
                Grade.canal_iptv_id == canal_iptv_id,
            ),
        )
    )
    if grade_versao_id_excluir:
        q = q.filter(Grade.grade_versao_id != grade_versao_id_excluir)

    row = q.first()
    if not row:
        return None
    grade, versao, turma, disc = row
    estudio = db.query(Estudio).filter(Estudio.id == grade.estudio_id).first()
    canal = db.query(CanalIptvModel).filter(CanalIptvModel.id == grade.canal_iptv_id).first()
    recurso = estudio.nome if estudio and grade.estudio_id == estudio_id else (canal.nome if canal else "N/A")
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    return {
        "turma": turma.nomenclatura_padrao or turma.nome,
        "disciplina": disc.nome,
        "dia_semana": dias[grade.dia_semana] if 0 <= grade.dia_semana <= 6 else str(grade.dia_semana),
        "horario": f"{grade.horario_inicio.strftime('%H:%M')} às {grade.horario_fim.strftime('%H:%M')}",
        "recurso_conflitante": recurso,
    }


# ─── Endpoint de verificação de choque (auxiliar frontend) ────────────

@router.post("/grade/verificar-choque")
def verificar_choque(
    data: ChoqueCheckIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Verifica choque global de horário. Retorna conflito=false ou detalhes do conflito."""
    try:
        h_ini = _parse_time(data.horario_inicio)
        h_fim = _parse_time(data.horario_fim)
    except ValueError as e:
        raise HTTPException(422, str(e))

    conflito = _verificar_choque(
        db, data.dia_semana, h_ini, h_fim,
        data.estudio_id, data.canal_iptv_id,
        data.grade_versao_id_excluir,
    )
    if conflito:
        return {"conflito": True, "detalhes": conflito}
    return {"conflito": False}


# ─── Grade Versão: listar e criar ─────────────────────────────────────

@router.get("/turmas/{turma_id}/grade-versao")
def listar_versoes(
    turma_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(404, "Turma não encontrada.")
    versoes = (
        db.query(GradeVersao)
        .filter(GradeVersao.turma_id == turma_id)
        .order_by(GradeVersao.data_criacao.desc())
        .all()
    )
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    resultado = []
    for v in versoes:
        slots = []
        for g in v.slots:
            disc = db.query(Disciplina).filter(Disciplina.id == g.disciplina_id).first()
            est = db.query(Estudio).filter(Estudio.id == g.estudio_id).first()
            canal = db.query(CanalIptvModel).filter(CanalIptvModel.id == g.canal_iptv_id).first()
            slots.append({
                "id": str(g.id),
                "dia_semana": g.dia_semana,
                "dia_semana_label": dias[g.dia_semana] if 0 <= g.dia_semana <= 6 else str(g.dia_semana),
                "horario_inicio": g.horario_inicio.strftime("%H:%M") if g.horario_inicio else None,
                "horario_fim": g.horario_fim.strftime("%H:%M") if g.horario_fim else None,
                "disciplina_id": str(g.disciplina_id) if g.disciplina_id else None,
                "disciplina_nome": disc.nome if disc else "N/A",
                "estudio_id": g.estudio_id,
                "estudio_nome": est.nome if est else "N/A",
                "canal_iptv_id": g.canal_iptv_id,
                "canal_nome": canal.nome if canal else "N/A",
                "tipo_slot": g.tipo_slot,
            })
        resultado.append({
            "id": v.id,
            "is_active": v.is_active,
            "data_ativacao": v.data_ativacao.isoformat() if v.data_ativacao else None,
            "data_criacao": v.data_criacao.isoformat(),
            "slots": slots,
        })
    return resultado


@router.post("/turmas/{turma_id}/grade-versao", status_code=201)
def criar_versao(
    turma_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(404, "Turma não encontrada.")
    versao = GradeVersao(turma_id=turma_id, is_active=False, criado_por=current_user.id)
    db.add(versao)
    db.commit()
    db.refresh(versao)
    return {"id": versao.id, "is_active": versao.is_active, "data_criacao": versao.data_criacao.isoformat()}


# ─── Grade Versão: listar e adicionar slots ───────────────────────────

@router.get("/turmas/{turma_id}/grade-versao/{versao_id}/slots")
def listar_slots_versao(
    turma_id: UUID,
    versao_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    versao = db.query(GradeVersao).filter(
        GradeVersao.id == versao_id, GradeVersao.turma_id == turma_id
    ).first()
    if not versao:
        raise HTTPException(404, "Versão não encontrada.")
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    slots = []
    for g in versao.slots:
        disc = db.query(Disciplina).filter(Disciplina.id == g.disciplina_id).first()
        slots.append({
            "id": str(g.id),
            "dia_semana": g.dia_semana,
            "dia_semana_label": dias[g.dia_semana] if 0 <= g.dia_semana <= 6 else str(g.dia_semana),
            "horario_inicio": g.horario_inicio.strftime("%H:%M") if g.horario_inicio else None,
            "horario_fim": g.horario_fim.strftime("%H:%M") if g.horario_fim else None,
            "disciplina_nome": disc.nome if disc else "N/A",
            "tipo_slot": g.tipo_slot,
        })
    return slots


@router.post("/turmas/{turma_id}/grade-versao/{versao_id}/slots", status_code=201)
def adicionar_slot(
    turma_id: UUID,
    versao_id: int,
    slot_in: SlotCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    versao = db.query(GradeVersao).filter(
        GradeVersao.id == versao_id, GradeVersao.turma_id == turma_id
    ).first()
    if not versao:
        raise HTTPException(404, "Versão não encontrada.")
    if versao.is_active:
        raise HTTPException(403, "Versão ativa é imutável. Crie uma nova versão para editar.")

    # Resolve horários
    if slot_in.slot_horario_id:
        slot_ref = db.query(SlotHorario).filter(SlotHorario.id == slot_in.slot_horario_id).first()
        if not slot_ref:
            raise HTTPException(422, "slot_horario_id inválido.")
        h_ini = slot_ref.horario_inicio
        h_fim = slot_ref.horario_fim
    elif slot_in.horario_inicio and slot_in.horario_fim:
        try:
            h_ini = _parse_time(slot_in.horario_inicio)
            h_fim = _parse_time(slot_in.horario_fim)
        except ValueError as e:
            raise HTTPException(422, str(e))
    else:
        raise HTTPException(422, "Informe slot_horario_id ou horario_inicio/horario_fim.")

    # Validar funcionamento do estúdio
    estudio = db.query(Estudio).filter(Estudio.id == slot_in.estudio_id, Estudio.ativo == True).first()
    if not estudio:
        raise HTTPException(422, "Estúdio inativo ou não encontrado.")
    if not estudio.funciona_24h:
        if not (estudio.horario_inicio <= h_ini and estudio.horario_fim >= h_fim):
            raise HTTPException(
                422,
                f"Estúdio '{estudio.nome}' não funciona nesse horário "
                f"({estudio.horario_inicio.strftime('%H:%M')}–{estudio.horario_fim.strftime('%H:%M')})."
            )

    # Verificar choque global
    conflito = _verificar_choque(
        db, slot_in.dia_semana, h_ini, h_fim,
        slot_in.estudio_id, slot_in.canal_iptv_id,
        versao_id,
    )
    if conflito:
        raise HTTPException(409, {"message": "Choque de horário detectado.", "detalhes": conflito})

    novo_slot = Grade(
        turma_id=turma_id,
        grade_versao_id=versao_id,
        slot_horario_id=slot_in.slot_horario_id,
        disciplina_id=slot_in.disciplina_id,
        estudio_id=slot_in.estudio_id,
        canal_iptv_id=slot_in.canal_iptv_id,
        tipo_slot=slot_in.tipo_slot,
        dia_semana=slot_in.dia_semana,
        horario_inicio=h_ini,
        horario_fim=h_fim,
    )
    db.add(novo_slot)
    db.commit()
    db.refresh(novo_slot)
    return {"id": str(novo_slot.id), "msg": "Slot adicionado."}


@router.delete("/turmas/{turma_id}/grade-versao/{versao_id}/slots/{slot_id}", status_code=204)
def remover_slot(
    turma_id: UUID,
    versao_id: int,
    slot_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    versao = db.query(GradeVersao).filter(
        GradeVersao.id == versao_id, GradeVersao.turma_id == turma_id
    ).first()
    if not versao:
        raise HTTPException(404, "Versão não encontrada.")
    if versao.is_active:
        raise HTTPException(403, "Versão ativa é imutável.")
    slot = db.query(Grade).filter(Grade.id == slot_id, Grade.grade_versao_id == versao_id).first()
    if not slot:
        raise HTTPException(404, "Slot não encontrado.")
    db.delete(slot)
    db.commit()


# ─── Grade Versão: ativar ────────────────────────────────────────────

@router.patch("/turmas/{turma_id}/grade-versao/{versao_id}/ativar")
def ativar_versao(
    turma_id: UUID,
    versao_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    versao = db.query(GradeVersao).filter(
        GradeVersao.id == versao_id, GradeVersao.turma_id == turma_id
    ).first()
    if not versao:
        raise HTTPException(404, "Versão não encontrada.")
    if versao.is_active:
        raise HTTPException(409, "Versão já está ativa.")
    if not versao.slots:
        raise HTTPException(422, "Não é possível ativar uma versão sem slots.")

    # Transação atômica: desativar versão atual, ativar nova
    try:
        db.query(GradeVersao).filter(
            GradeVersao.turma_id == turma_id,
            GradeVersao.is_active == True,
        ).update({"is_active": False})
        versao.is_active = True
        versao.data_ativacao = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Falha ao ativar versão. Tente novamente.")

    return {"message": "Versão ativada com sucesso.", "id": versao.id}
```

- [ ] **Step 2: Commit**

```bash
git add app/api/rotas_grade_versao.py
git commit -m "feat: endpoints grade-versao - CRUD, slots, ativar e verificar-choque global"
```

---

## Task 5: Modificar `POST /turmas` para exigir grade

**Files:**
- Modify: `app/api/rotas_turma.py`

- [ ] **Step 1: Adicionar schema `SlotCreateIn` e `GradeCreateIn` no topo de `rotas_turma.py`**

Após os imports existentes, adicionar:

```python
from app.models.infraestrutura import GradeVersao, Estudio, CanalIptvModel, SlotHorario
from app.api.rotas_grade_versao import _verificar_choque, _parse_time
```

E antes da classe `TurmaCreate`, adicionar:

```python
class SlotTurmaCreate(BaseModel):
    slot_horario_id: Optional[int] = None
    dia_semana: int
    disciplina_id: UUID
    estudio_id: int
    canal_iptv_id: int
    tipo_slot: str = "aula"
    horario_inicio: Optional[str] = None
    horario_fim: Optional[str] = None


class GradeTurmaCreate(BaseModel):
    slots: List[SlotTurmaCreate]
```

E modificar `TurmaCreate` para incluir grade:

```python
class TurmaCreate(BaseModel):
    unit_id: Optional[UUID] = None
    nome: str
    modalidade: str
    serie_modulo: str
    turno: str
    nomenclatura_padrao: Optional[str] = None
    grade: Optional[GradeTurmaCreate] = None  # obrigatório em criação nova
```

- [ ] **Step 2: Modificar o handler `criar_turma` para exigir grade com slots**

Após a verificação de duplicidade (linha ~107) e antes do `nova_turma = Turma(...)`, adicionar:

```python
    # Validação de grade obrigatória
    if not turma.grade or not turma.grade.slots:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uma turma deve ter ao menos um slot de grade para ser criada.",
        )

    # Validar todos os slots ANTES de salvar qualquer dado
    slots_para_criar = []
    from app.models.auxiliares import Grade as GradeModel
    from app.api.rotas_grade_versao import _verificar_choque as check_choque, _parse_time as parse_t
    
    for slot_in in turma.grade.slots:
        if slot_in.slot_horario_id:
            slot_ref = db.query(SlotHorario).filter(SlotHorario.id == slot_in.slot_horario_id).first()
            if not slot_ref:
                raise HTTPException(422, f"slot_horario_id {slot_in.slot_horario_id} inválido.")
            h_ini = slot_ref.horario_inicio
            h_fim = slot_ref.horario_fim
        elif slot_in.horario_inicio and slot_in.horario_fim:
            h_ini = parse_t(slot_in.horario_inicio)
            h_fim = parse_t(slot_in.horario_fim)
        else:
            raise HTTPException(422, "Informe slot_horario_id ou horario_inicio/horario_fim em cada slot.")
        
        conflito = check_choque(db, slot_in.dia_semana, h_ini, h_fim, slot_in.estudio_id, slot_in.canal_iptv_id)
        if conflito:
            raise HTTPException(409, {"message": "Choque de horário detectado em um dos slots.", "detalhes": conflito})
        
        slots_para_criar.append((slot_in, h_ini, h_fim))
```

- [ ] **Step 3: Dentro do bloco `try` de `criar_turma`, após criar a turma, criar `GradeVersao` e slots**

Substituir o bloco `try` existente:

```python
    nova_turma = Turma(
        unit_id=turma.unit_id,
        nome=turma.nome,
        modalidade=turma.modalidade,
        serie_modulo=turma.serie_modulo,
        turno=turno_upper,
        nomenclatura_padrao=turma.nomenclatura_padrao,
    )

    db.add(nova_turma)
    try:
        db.flush()  # gera o ID sem comitar

        # Criar GradeVersao ativa
        versao = GradeVersao(
            turma_id=nova_turma.id,
            is_active=True,
            data_ativacao=datetime.utcnow(),
            criado_por=current_user.id,
        )
        db.add(versao)
        db.flush()

        # Criar slots
        from app.models.auxiliares import Grade as GradeModel
        for slot_in, h_ini, h_fim in slots_para_criar:
            slot = GradeModel(
                turma_id=nova_turma.id,
                grade_versao_id=versao.id,
                slot_horario_id=slot_in.slot_horario_id,
                disciplina_id=slot_in.disciplina_id,
                estudio_id=slot_in.estudio_id,
                canal_iptv_id=slot_in.canal_iptv_id,
                tipo_slot=slot_in.tipo_slot,
                dia_semana=slot_in.dia_semana,
                horario_inicio=h_ini,
                horario_fim=h_fim,
            )
            db.add(slot)

        db.commit()
        db.refresh(nova_turma)
        return nova_turma
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Colisão de dados ao gravar turma.",
        )
```

- [ ] **Step 4: Atualizar `listar_grade_turma` para usar `dia_semana` como integer e retornar info de versão**

Localizar `listar_grade_turma` (linha ~215). Substituir o mapeamento `reports_map` e o loop `for g in grades` para usar `dia_semana` integer:

```python
    # Filtrar grade por versão ativa (novo sistema)
    from app.models.infraestrutura import GradeVersao
    versao_ativa = db.query(GradeVersao).filter(
        GradeVersao.turma_id == turma_id,
        GradeVersao.is_active == True,
    ).first()
```

E no resultado de cada grade slot, mapear `dia_semana` integer → string:

```python
    DIAS_MAP = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"}
    # ...
    "dia_semana": DIAS_MAP.get(g.dia_semana, str(g.dia_semana)),
```

- [ ] **Step 5: Commit**

```bash
git add app/api/rotas_turma.py
git commit -m "feat: POST /turmas exige grade com slots, listar_grade_turma usa dia_semana int"
```

---

## Task 6: Atualizar `rotas_live.py` para `dia_semana` integer

**Files:**
- Modify: `app/api/rotas_live.py`

- [ ] **Step 1: Substituir a lógica de `dia_atual` (string) por integer**

Em `rotas_live.py`, localizar e substituir:

```python
# ANTES:
dia_semana_map = {
    0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta",
    4: "Sexta", 5: "Sábado", 6: "Domingo"
}
dia_atual = dia_semana_map[hoje.weekday()]
# ...
.filter(Grade.dia_semana == dia_atual)
```

Por:

```python
# DEPOIS:
dia_atual_int = hoje.weekday()  # 0=Segunda…6=Domingo
# ...
.filter(Grade.dia_semana == dia_atual_int)
```

- [ ] **Step 2: Commit**

```bash
git add app/api/rotas_live.py
git commit -m "fix: rotas_live usa dia_semana como integer (0-6)"
```

---

## Task 7: Registrar novos routers em `app/main.py` e remover rotas antigas

**Files:**
- Modify: `app/main.py`
- Delete: `app/api/rotas_grade.py`

- [ ] **Step 1: Adicionar imports dos novos routers em `app/main.py`**

Localizar os imports de rotas e adicionar:

```python
from app.api.rotas_configuracoes import router as configuracoes_router
from app.api.rotas_grade_versao import router as grade_versao_router
```

Remover:

```python
from app.api.rotas_grade import router as grade_router
```

- [ ] **Step 2: Registrar novos routers e remover o antigo**

Localizar `app.include_router(grade_router)` e substituir por:

```python
app.include_router(configuracoes_router)
app.include_router(grade_versao_router)
```

- [ ] **Step 3: Adicionar novos modelos no import de `app/main.py`**

Localizar o bloco de imports de modelos e adicionar:

```python
from app.models import (  # noqa: F401
    AuditLog,
    ClassReport,
    Disciplina,
    DiretorImagem,
    Estudio,
    CanalIptvModel,
    SlotHorario,
    GradeVersao,
    Grade,
    Professor,
    ProfessorDisciplina,
    Turma,
    Unit,
    User,
)
```

- [ ] **Step 4: Adicionar rota de página de configurações**

Após a rota `/admin/cadastros`, adicionar:

```python
@app.get("/admin/configuracoes")
def admin_configuracoes_page(request: Request):
    """Tela de configuração de infraestrutura — estudios, canais IPTV, slots de horário."""
    return templates.TemplateResponse("admin_configuracoes.html", {"request": request})
```

- [ ] **Step 5: Deletar arquivo antigo**

```bash
del "app\api\rotas_grade.py"
```

- [ ] **Step 6: Reiniciar container e verificar**

```bash
docker compose restart api
docker compose logs api --tail=30
```

Expected: sem erros de import. Aplicação inicia normalmente.

- [ ] **Step 7: Commit**

```bash
git add app/main.py
git rm app/api/rotas_grade.py
git commit -m "refact: registra novos routers de configuracoes e grade-versao, remove rotas_grade.py"
```

---

## Task 8: Frontend — Página de Configurações de Infraestrutura

**Files:**
- Create: `app/templates/admin_configuracoes.html`

- [ ] **Step 1: Criar `app/templates/admin_configuracoes.html`**

```html
{% extends "base.html" %}
{% block title %}Configurações — Canal Educação{% endblock %}

{% block content %}
<div class="page-header">
    <div>
        <h1 class="page-title">⚙️ Configurações de Infraestrutura</h1>
        <p class="page-subtitle">Estúdios, Canais IPTV e Slots de Horário</p>
    </div>
</div>

<!-- Tabs -->
<div class="tabs" style="margin-bottom: 1.5rem;">
    <button class="tab-btn active" onclick="switchTab('estudios')" id="tab-estudios">🏢 Estúdios</button>
    <button class="tab-btn" onclick="switchTab('canais')" id="tab-canais">📡 Canais IPTV</button>
    <button class="tab-btn" onclick="switchTab('slots')" id="tab-slots">🕐 Slots de Horário</button>
</div>

<!-- ═══ Estúdios ═══ -->
<div class="card" id="panel-estudios">
    <div class="card-header">
        <h3 class="card-title">🏢 Estúdios</h3>
        <button class="btn btn-primary btn-sm" onclick="openModal('estudio')">+ Novo Estúdio</button>
    </div>
    <div id="estudios-table"><div class="spinner"></div></div>
</div>

<!-- ═══ Canais IPTV ═══ -->
<div class="card" id="panel-canais" style="display:none;">
    <div class="card-header">
        <h3 class="card-title">📡 Canais IPTV</h3>
        <button class="btn btn-primary btn-sm" onclick="openModal('canal')">+ Novo Canal</button>
    </div>
    <div id="canais-table"><div class="spinner"></div></div>
</div>

<!-- ═══ Slots de Horário ═══ -->
<div class="card" id="panel-slots" style="display:none;">
    <div class="card-header">
        <h3 class="card-title">🕐 Slots de Horário</h3>
        <select id="slot-turno-filter" class="form-select" style="width:200px;" onchange="loadSlots()">
            <option value="">Todos os turnos</option>
            <option value="manha">Manhã</option>
            <option value="tarde">Tarde</option>
            <option value="noite">Noite</option>
            <option value="madrugada">Madrugada</option>
        </select>
        <button class="btn btn-primary btn-sm" onclick="openModal('slot')">+ Novo Slot</button>
    </div>
    <div id="slots-table"><div class="spinner"></div></div>
</div>

<!-- Modal genérico -->
<div class="modal-overlay" id="modal-overlay" onclick="closeModal()" style="display:none;"></div>
<div class="modal" id="modal" style="display:none;">
    <div class="modal-header">
        <h3 id="modal-title">Novo Item</h3>
        <button onclick="closeModal()" class="drawer-close">✕</button>
    </div>
    <div class="modal-body" id="modal-body"></div>
</div>

{% endblock %}

{% block scripts %}
<script>
const TOKEN = () => localStorage.getItem('token') || localStorage.getItem('access_token');
const H = () => ({ 'Authorization': `Bearer ${TOKEN()}`, 'Content-Type': 'application/json' });

document.addEventListener('DOMContentLoaded', () => {
    if (!TOKEN()) { window.location.href = '/'; return; }
    loadUserProfile();
    loadEstudios();
});

function switchTab(tab) {
    ['estudios','canais','slots'].forEach(t => {
        document.getElementById(`panel-${t}`).style.display = t === tab ? 'block' : 'none';
        document.getElementById(`tab-${t}`).classList.toggle('active', t === tab);
    });
    if (tab === 'estudios') loadEstudios();
    if (tab === 'canais') loadCanais();
    if (tab === 'slots') loadSlots();
}

// ── Estúdios ────────────────────────────────────────────────────────
async function loadEstudios() {
    const res = await fetch('/api/v1/configuracoes/estudios', { headers: H() });
    if (!res.ok) { showToast('Erro ao carregar estúdios', 'error'); return; }
    const data = await res.json();
    const el = document.getElementById('estudios-table');
    if (!data.length) { el.innerHTML = '<p style="padding:1rem;color:var(--text-muted)">Nenhum estúdio cadastrado.</p>'; return; }
    el.innerHTML = `<table class="table">
        <thead><tr><th>ID</th><th>Nome</th><th>Horário</th><th>24h</th><th>Status</th><th>Ações</th></tr></thead>
        <tbody>${data.map(e => `<tr>
            <td>${e.id}</td><td>${e.nome}</td>
            <td>${e.funciona_24h ? '—' : `${e.horario_inicio} às ${e.horario_fim}`}</td>
            <td>${e.funciona_24h ? '✅' : '—'}</td>
            <td><span class="badge ${e.ativo ? 'badge-green' : 'badge-red'}">${e.ativo ? 'Ativo' : 'Inativo'}</span></td>
            <td>
                <button class="btn btn-sm btn-secondary" onclick='editEstudio(${JSON.stringify(e)})'>Editar</button>
                ${e.ativo ? `<button class="btn btn-sm btn-danger" onclick="desativarEstudio(${e.id})">Desativar</button>` : ''}
            </td>
        </tr>`).join('')}</tbody>
    </table>`;
}

function openModal(type, data = null) {
    document.getElementById('modal-overlay').style.display = 'block';
    document.getElementById('modal').style.display = 'block';
    if (type === 'estudio') renderEstudioForm(data);
    if (type === 'canal') renderCanalForm(data);
    if (type === 'slot') renderSlotForm(data);
}
function closeModal() {
    document.getElementById('modal-overlay').style.display = 'none';
    document.getElementById('modal').style.display = 'none';
}

function renderEstudioForm(e = null) {
    document.getElementById('modal-title').textContent = e ? 'Editar Estúdio' : 'Novo Estúdio';
    document.getElementById('modal-body').innerHTML = `
        <form onsubmit="saveEstudio(event, ${e ? e.id : 'null'})">
            <div class="form-group"><label class="form-label">Nome</label>
                <input class="form-input" id="e-nome" value="${e ? e.nome : ''}" required></div>
            <label style="display:flex;align-items:center;gap:8px;margin-bottom:1rem;">
                <input type="checkbox" id="e-24h" onchange="toggle24h()" ${e && e.funciona_24h ? 'checked' : ''}> Funciona 24h
            </label>
            <div id="e-horarios" ${e && e.funciona_24h ? 'style="display:none"' : ''}>
                <div class="form-row">
                    <div class="form-group"><label class="form-label">Início</label>
                        <input type="time" class="form-input" id="e-ini" value="${e ? e.horario_inicio : '07:00'}" required></div>
                    <div class="form-group"><label class="form-label">Fim</label>
                        <input type="time" class="form-input" id="e-fim" value="${e ? e.horario_fim : '23:00'}" required></div>
                </div>
            </div>
            <div style="display:flex;gap:1rem;margin-top:1.5rem;">
                <button type="button" class="btn btn-secondary" style="flex:1" onclick="closeModal()">Cancelar</button>
                <button type="submit" class="btn btn-primary" style="flex:2">Salvar</button>
            </div>
        </form>`;
}
function toggle24h() {
    const c = document.getElementById('e-24h').checked;
    document.getElementById('e-horarios').style.display = c ? 'none' : 'block';
}
async function saveEstudio(ev, id) {
    ev.preventDefault();
    const body = {
        nome: document.getElementById('e-nome').value,
        horario_inicio: document.getElementById('e-ini').value || '00:00',
        horario_fim: document.getElementById('e-fim').value || '23:59',
        funciona_24h: document.getElementById('e-24h').checked,
    };
    const url = id ? `/api/v1/configuracoes/estudios/${id}` : '/api/v1/configuracoes/estudios';
    const method = id ? 'PATCH' : 'POST';
    const res = await fetch(url, { method, headers: H(), body: JSON.stringify(body) });
    if (res.ok) { closeModal(); loadEstudios(); showToast('Estúdio salvo!'); }
    else { const d = await res.json(); showToast(d.detail || 'Erro', 'error'); }
}
function editEstudio(e) { openModal('estudio', e); }
async function desativarEstudio(id) {
    if (!confirm('Desativar este estúdio? Grades existentes não serão afetadas.')) return;
    const res = await fetch(`/api/v1/configuracoes/estudios/${id}`, { method: 'DELETE', headers: H() });
    if (res.ok || res.status === 204) { loadEstudios(); showToast('Estúdio desativado.'); }
    else showToast('Erro ao desativar.', 'error');
}

// ── Canais IPTV ─────────────────────────────────────────────────────
async function loadCanais() {
    const res = await fetch('/api/v1/configuracoes/canais-iptv', { headers: H() });
    if (!res.ok) { showToast('Erro ao carregar canais', 'error'); return; }
    const data = await res.json();
    const el = document.getElementById('canais-table');
    if (!data.length) { el.innerHTML = '<p style="padding:1rem;color:var(--text-muted)">Nenhum canal cadastrado.</p>'; return; }
    el.innerHTML = `<table class="table">
        <thead><tr><th>Nº</th><th>Nome</th><th>Status</th><th>Ações</th></tr></thead>
        <tbody>${data.map(c => `<tr>
            <td>${c.numero}</td><td>${c.nome}</td>
            <td><span class="badge ${c.ativo ? 'badge-green' : 'badge-red'}">${c.ativo ? 'Ativo' : 'Inativo'}</span></td>
            <td>
                <button class="btn btn-sm btn-secondary" onclick='editCanal(${JSON.stringify(c)})'>Editar</button>
                ${c.ativo ? `<button class="btn btn-sm btn-danger" onclick="desativarCanal(${c.id})">Desativar</button>` : ''}
            </td>
        </tr>`).join('')}</tbody>
    </table>`;
}
function renderCanalForm(c = null) {
    document.getElementById('modal-title').textContent = c ? 'Editar Canal' : 'Novo Canal IPTV';
    document.getElementById('modal-body').innerHTML = `
        <form onsubmit="saveCanal(event, ${c ? c.id : 'null'})">
            <div class="form-group"><label class="form-label">Nome</label>
                <input class="form-input" id="c-nome" value="${c ? c.nome : ''}" required></div>
            <div class="form-group"><label class="form-label">Número</label>
                <input type="number" class="form-input" id="c-num" value="${c ? c.numero : ''}" required></div>
            <div style="display:flex;gap:1rem;margin-top:1.5rem;">
                <button type="button" class="btn btn-secondary" style="flex:1" onclick="closeModal()">Cancelar</button>
                <button type="submit" class="btn btn-primary" style="flex:2">Salvar</button>
            </div>
        </form>`;
}
async function saveCanal(ev, id) {
    ev.preventDefault();
    const body = { nome: document.getElementById('c-nome').value, numero: parseInt(document.getElementById('c-num').value) };
    const url = id ? `/api/v1/configuracoes/canais-iptv/${id}` : '/api/v1/configuracoes/canais-iptv';
    const res = await fetch(url, { method: id ? 'PATCH' : 'POST', headers: H(), body: JSON.stringify(body) });
    if (res.ok) { closeModal(); loadCanais(); showToast('Canal salvo!'); }
    else { const d = await res.json(); showToast(d.detail || 'Erro', 'error'); }
}
function editCanal(c) { openModal('canal', c); }
async function desativarCanal(id) {
    if (!confirm('Desativar este canal?')) return;
    const res = await fetch(`/api/v1/configuracoes/canais-iptv/${id}`, { method: 'DELETE', headers: H() });
    if (res.ok || res.status === 204) { loadCanais(); showToast('Canal desativado.'); }
    else showToast('Erro', 'error');
}

// ── Slots de Horário ─────────────────────────────────────────────────
async function loadSlots() {
    const turno = document.getElementById('slot-turno-filter').value;
    const url = '/api/v1/configuracoes/slots-horario' + (turno ? `?turno=${turno}` : '');
    const res = await fetch(url, { headers: H() });
    if (!res.ok) { showToast('Erro ao carregar slots', 'error'); return; }
    const data = await res.json();
    const el = document.getElementById('slots-table');
    if (!data.length) { el.innerHTML = '<p style="padding:1rem;color:var(--text-muted)">Nenhum slot cadastrado.</p>'; return; }
    el.innerHTML = `<table class="table">
        <thead><tr><th>Turno</th><th>Ordem</th><th>Início</th><th>Fim</th><th>Duração</th><th>Status</th><th>Ações</th></tr></thead>
        <tbody>${data.map(s => {
            const dur = s.horario_inicio && s.horario_fim ? calcDur(s.horario_inicio, s.horario_fim) : '—';
            return `<tr>
                <td><span class="badge badge-blue">${s.turno}</span></td>
                <td>${s.ordem}º</td><td>${s.horario_inicio}</td><td>${s.horario_fim}</td>
                <td>${dur} min</td>
                <td><span class="badge ${s.ativo ? 'badge-green' : 'badge-red'}">${s.ativo ? 'Ativo' : 'Inativo'}</span></td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick='editSlot(${JSON.stringify(s)})'>Editar</button>
                    ${s.ativo ? `<button class="btn btn-sm btn-danger" onclick="desativarSlot(${s.id})">Desativar</button>` : ''}
                </td>
            </tr>`;
        }).join('')}</tbody>
    </table>`;
}
function calcDur(ini, fim) {
    const [h1,m1] = ini.split(':').map(Number);
    const [h2,m2] = fim.split(':').map(Number);
    return (h2*60+m2) - (h1*60+m1);
}
function renderSlotForm(s = null) {
    document.getElementById('modal-title').textContent = s ? 'Editar Slot' : 'Novo Slot de Horário';
    document.getElementById('modal-body').innerHTML = `
        <form onsubmit="saveSlot(event, ${s ? s.id : 'null'})">
            <div class="form-group"><label class="form-label">Turno</label>
                <select class="form-select" id="s-turno" required>
                    <option value="manha" ${s && s.turno==='manha' ? 'selected':''}>Manhã (05:00–12:00)</option>
                    <option value="tarde" ${s && s.turno==='tarde' ? 'selected':''}>Tarde (12:00–18:00)</option>
                    <option value="noite" ${s && s.turno==='noite' ? 'selected':''}>Noite (18:00–00:00)</option>
                    <option value="madrugada" ${s && s.turno==='madrugada' ? 'selected':''}>Madrugada (00:00–05:00)</option>
                </select>
            </div>
            <div class="form-group"><label class="form-label">Ordem (posição na exibição)</label>
                <input type="number" class="form-input" id="s-ordem" value="${s ? s.ordem : 1}" min="1" required></div>
            <div class="form-row">
                <div class="form-group"><label class="form-label">Início</label>
                    <input type="time" class="form-input" id="s-ini" value="${s ? s.horario_inicio : ''}" required></div>
                <div class="form-group"><label class="form-label">Fim</label>
                    <input type="time" class="form-input" id="s-fim" value="${s ? s.horario_fim : ''}" required></div>
            </div>
            <div id="dur-preview" style="font-size:0.8rem;color:var(--text-muted);margin-top:-0.5rem;"></div>
            <div style="display:flex;gap:1rem;margin-top:1.5rem;">
                <button type="button" class="btn btn-secondary" style="flex:1" onclick="closeModal()">Cancelar</button>
                <button type="submit" class="btn btn-primary" style="flex:2">Salvar</button>
            </div>
        </form>`;
    document.getElementById('s-ini').addEventListener('input', updateDurPreview);
    document.getElementById('s-fim').addEventListener('input', updateDurPreview);
}
function updateDurPreview() {
    const ini = document.getElementById('s-ini').value;
    const fim = document.getElementById('s-fim').value;
    if (ini && fim) {
        const dur = calcDur(ini, fim);
        document.getElementById('dur-preview').textContent = dur > 0 ? `Duração: ${dur} minutos` : 'Horário inválido';
    }
}
async function saveSlot(ev, id) {
    ev.preventDefault();
    const body = {
        turno: document.getElementById('s-turno').value,
        ordem: parseInt(document.getElementById('s-ordem').value),
        horario_inicio: document.getElementById('s-ini').value,
        horario_fim: document.getElementById('s-fim').value,
    };
    const url = id ? `/api/v1/configuracoes/slots-horario/${id}` : '/api/v1/configuracoes/slots-horario';
    const res = await fetch(url, { method: id ? 'PATCH' : 'POST', headers: H(), body: JSON.stringify(body) });
    if (res.ok) { closeModal(); loadSlots(); showToast('Slot salvo!'); }
    else { const d = await res.json(); showToast(d.detail || 'Erro ao salvar slot', 'error'); }
}
function editSlot(s) { openModal('slot', s); }
async function desativarSlot(id) {
    if (!confirm('Desativar este slot?')) return;
    const res = await fetch(`/api/v1/configuracoes/slots-horario/${id}`, { method: 'DELETE', headers: H() });
    if (res.ok || res.status === 204) { loadSlots(); showToast('Slot desativado.'); }
    else showToast('Erro', 'error');
}
</script>
{% endblock %}
```

- [ ] **Step 2: Adicionar link de navegação no menu (se existir menu em `base.html`)**

Verificar se `base.html` tem sidebar/nav com link para `/admin/cadastros`. Se sim, adicionar também link para `/admin/configuracoes`.

- [ ] **Step 3: Verificar no navegador**

Acessar `http://localhost:8000/admin/configuracoes` e confirmar que as três abas (Estúdios, Canais IPTV, Slots) carregam sem erros de JS/network.

- [ ] **Step 4: Commit**

```bash
git add app/templates/admin_configuracoes.html
git commit -m "feat: página de configurações de infraestrutura - estudios, canais IPTV, slots"
```

---

## Task 9: Frontend — Aba de Grade Versão na página de Cadastros

**Files:**
- Modify: `app/templates/admin_cadastros.html`

- [ ] **Step 1: Substituir o conteúdo da aba "Gestão de Grades" no `admin_cadastros.html`**

Localizar `<!-- ═══ Grades Tab (Task 07) ═══ -->` e substituir todo o painel `id="panel-grades"` pelo seguinte:

```html
<!-- ═══ Grades Tab (v2) ═══ -->
<div id="panel-grades" style="display: none;">
    <div class="card" style="margin-bottom: 1.5rem;">
        <div class="card-header">
            <h3 class="card-title">🗓️ Gestão de Grade por Turma</h3>
        </div>
        <div class="card-body" style="padding: 1.5rem;">
            <div class="form-group">
                <label class="form-label">Selecionar Turma</label>
                <select id="gv-turma-select" class="form-select" onchange="loadGradeVersoes()">
                    <option value="">Selecione uma turma...</option>
                </select>
            </div>
            <div id="gv-versoes-container" style="display:none; margin-top: 1.5rem;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 1rem;">
                    <h4 style="margin:0;">Versões da Grade</h4>
                    <button class="btn btn-primary btn-sm" onclick="criarNovaVersao()">+ Nova Versão</button>
                </div>
                <div id="gv-versoes-list"></div>
            </div>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Adicionar o JavaScript da aba de grades no bloco `<script>` de `admin_cadastros.html`**

Ao final do bloco `<script>` existente, antes do fechamento `</script>`, adicionar:

```javascript
// ── Grade Versão ────────────────────────────────────────────────────
async function loadGradeTurmas() {
    const token = localStorage.getItem('token') || localStorage.getItem('access_token');
    const res = await fetch('/api/v1/turmas/', { headers: { 'Authorization': `Bearer ${token}` } });
    if (!res.ok) return;
    const turmas = await res.json();
    const sel = document.getElementById('gv-turma-select');
    if (!sel) return;
    sel.innerHTML = '<option value="">Selecione uma turma...</option>' +
        turmas.map(t => `<option value="${t.id}">${t.nomenclatura_padrao || t.nome} (${t.turno})</option>`).join('');
}

async function loadGradeVersoes() {
    const token = localStorage.getItem('token') || localStorage.getItem('access_token');
    const turmaId = document.getElementById('gv-turma-select').value;
    if (!turmaId) { document.getElementById('gv-versoes-container').style.display = 'none'; return; }
    document.getElementById('gv-versoes-container').style.display = 'block';
    
    const res = await fetch(`/api/v1/turmas/${turmaId}/grade-versao`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) { showToast('Erro ao carregar versões', 'error'); return; }
    const versoes = await res.json();
    const container = document.getElementById('gv-versoes-list');
    
    if (!versoes.length) {
        container.innerHTML = '<p style="color:var(--text-muted)">Nenhuma versão de grade para esta turma.</p>';
        return;
    }
    
    container.innerHTML = versoes.map(v => `
        <div class="card" style="margin-bottom:1rem; border-left: 4px solid ${v.is_active ? 'var(--success)' : 'var(--border-color)'};">
            <div class="card-header" style="padding: 0.75rem 1rem;">
                <div>
                    <span class="badge ${v.is_active ? 'badge-green' : 'badge-yellow'}">${v.is_active ? 'ATIVA' : 'INATIVA'}</span>
                    <span style="margin-left:0.5rem; font-size:0.85rem; color:var(--text-muted)">
                        Criada em ${new Date(v.data_criacao).toLocaleDateString('pt-BR')}
                        ${v.data_ativacao ? ' · Ativada em ' + new Date(v.data_ativacao).toLocaleDateString('pt-BR') : ''}
                    </span>
                </div>
                <div>
                    ${!v.is_active ? `<button class="btn btn-sm btn-primary" onclick="ativarVersao('${turmaId}', ${v.id})">Ativar</button>` : ''}
                    <button class="btn btn-sm btn-secondary" onclick="toggleSlotsView(${v.id})">Ver Slots (${v.slots.length})</button>
                </div>
            </div>
            <div id="slots-view-${v.id}" style="display:none; padding: 1rem;">
                ${v.slots.length ? `<table class="table"><thead><tr><th>Dia</th><th>Horário</th><th>Disciplina</th><th>Estúdio</th><th>Canal</th><th>Tipo</th></tr></thead><tbody>
                    ${v.slots.map(s => `<tr>
                        <td>${s.dia_semana_label}</td>
                        <td>${s.horario_inicio} às ${s.horario_fim}</td>
                        <td>${s.disciplina_nome}</td>
                        <td>${s.estudio_nome}</td>
                        <td>${s.canal_nome}</td>
                        <td><span class="badge ${s.tipo_slot === 'aula' ? 'badge-blue' : 'badge-orange'}">${s.tipo_slot}</span></td>
                    </tr>`).join('')}
                </tbody></table>` : '<p style="color:var(--text-muted)">Sem slots nesta versão.</p>'}
            </div>
        </div>
    `).join('');
}

function toggleSlotsView(versaoId) {
    const el = document.getElementById(`slots-view-${versaoId}`);
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

async function criarNovaVersao() {
    const token = localStorage.getItem('token') || localStorage.getItem('access_token');
    const turmaId = document.getElementById('gv-turma-select').value;
    if (!turmaId) return;
    const res = await fetch(`/api/v1/turmas/${turmaId}/grade-versao`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    if (res.ok) { showToast('Nova versão criada! Adicione slots via API.'); loadGradeVersoes(); }
    else { const d = await res.json(); showToast(d.detail || 'Erro', 'error'); }
}

async function ativarVersao(turmaId, versaoId) {
    if (!confirm('Ativar esta versão? A grade ativa atual será substituída. Relatórios anteriores não serão afetados.')) return;
    const token = localStorage.getItem('token') || localStorage.getItem('access_token');
    const res = await fetch(`/api/v1/turmas/${turmaId}/grade-versao/${versaoId}/ativar`, {
        method: 'PATCH',
        headers: { 'Authorization': `Bearer ${token}` },
    });
    if (res.ok) { showToast('Versão ativada com sucesso!'); loadGradeVersoes(); }
    else { const d = await res.json(); showToast(d.detail || 'Erro', 'error'); }
}
```

- [ ] **Step 3: Ajustar a função `switchTab` para carregar turmas quando a aba grades for selecionada**

Localizar a função `switchTab` existente e adicionar ao ramo `grades`:

```javascript
// Dentro de switchTab, adicionar:
if (tab === 'grades') loadGradeTurmas();
```

- [ ] **Step 4: Testar no navegador**

Acessar `/admin/cadastros`, clicar na aba "Gestão de Grades", selecionar uma turma e verificar se as versões são listadas.

- [ ] **Step 5: Commit**

```bash
git add app/templates/admin_cadastros.html
git commit -m "feat: aba de gestão de grade-versao em admin_cadastros, substituindo upload de planilha"
```

---

## Task 10: Atualizar `grade.html` para mostrar dia_semana como integer e integrar com versão ativa

**Files:**
- Modify: `app/templates/grade.html`

- [ ] **Step 1: Atualizar o `DIAS_SEMANA` array e o mapeamento reverso em `grade.html`**

Localizar no `<script>` de `grade.html`:

```javascript
const DIAS_SEMANA = ['SEGUNDA', 'TERÇA', 'QUARTA', 'QUINTA', 'SEXTA', 'SÁBADO', 'DOMINGO'];
```

O array continua o mesmo (correto — índice 0=Segunda). A mudança é que agora `g.dia_semana` vem como integer (0-6) ao invés de string. O frontend já usa índice numérico para os dias da semana via `getWeekDates()`.

Localizar a função que constrói a matriz (onde compara `dia_semana` com dia da semana) e verificar que usa comparação numérica. Se estiver comparando com strings, atualizar para comparação com índice inteiro.

Localizar no código onde `dia_semana` é comparado (busca por `g.dia_semana` no script):

```javascript
// ANTES (se existir):
const colIndex = DIAS_SEMANA.indexOf(g.dia_semana.toUpperCase());

// DEPOIS:
const colIndex = typeof g.dia_semana === 'number' ? g.dia_semana : DIAS_SEMANA.indexOf(g.dia_semana.toUpperCase());
```

- [ ] **Step 2: Atualizar o modal de adição de slot em `grade.html`**

O modal `grade-form` atual tem um `<select id="grade-dia">` com strings ("Segunda", "Terça"...). Deve enviar o índice inteiro ao invés da string.

Localizar:
```html
<select id="grade-dia" class="form-select" required>
    <option>Segunda</option>
    ...
</select>
```

Substituir por:
```html
<select id="grade-dia" class="form-select" required>
    <option value="0">Segunda</option>
    <option value="1">Terça</option>
    <option value="2">Quarta</option>
    <option value="3">Quinta</option>
    <option value="4">Sexta</option>
    <option value="5">Sábado</option>
    <option value="6">Domingo</option>
</select>
```

- [ ] **Step 3: Atualizar o endpoint POST no `saveGradeSlot` para enviar `dia_semana` como integer**

Localizar a função `saveGradeSlot` e garantir que o body enviado ao `POST /api/v1/turmas/{id}/grade` envia `dia_semana` como número inteiro:

```javascript
const body = {
    disciplina_id: ...,
    dia_semana: parseInt(document.getElementById('grade-dia').value),
    horario_inicio: ...,
    horario_fim: ...,
    canal_iptv: ...,
};
```

- [ ] **Step 4: Commit**

```bash
git add app/templates/grade.html
git commit -m "fix: grade.html usa dia_semana como integer (0-6) no select e no body POST"
```

---

## Task 11: Seed de Dados de Infraestrutura

Após a migration ter rodado, o sistema precisa de dados básicos de estúdios e canais para que o novo fluxo funcione.

- [ ] **Step 1: Criar seed de estudios via API (ou diretamente no banco)**

```bash
docker compose exec db psql -U assistente_professores postgres-prd -c "
INSERT INTO estudio (nome, horario_inicio, horario_fim, funciona_24h, ativo) VALUES
  ('Estúdio 01', '05:00', '23:59', false, true),
  ('Estúdio 02', '05:00', '23:59', false, true),
  ('Estúdio 03', '05:00', '23:59', false, true),
  ('Estúdio 04', '05:00', '23:59', false, true),
  ('Estúdio 05', '05:00', '23:59', false, true),
  ('Estúdio 06', '05:00', '23:59', false, true),
  ('Estúdio 07', '05:00', '23:59', false, true),
  ('Estúdio 08', '05:00', '23:59', false, true),
  ('Estúdio 09', '05:00', '23:59', false, true),
  ('Externo', '00:00', '23:59', true, true)
ON CONFLICT DO NOTHING;
"
```

- [ ] **Step 2: Seed de canais IPTV a partir dos valores existentes na tabela grades**

```bash
docker compose exec db psql -U assistente_professores postgres-prd -c "
INSERT INTO canal_iptv (nome, numero, ativo)
SELECT DISTINCT 'Canal ' || canal_iptv, canal_iptv, true
FROM grades
WHERE canal_iptv IS NOT NULL
ORDER BY canal_iptv
ON CONFLICT (numero) DO NOTHING;
"
```

- [ ] **Step 3: Seed de slots de horário a partir dos horários existentes nas grades**

```bash
docker compose exec db psql -U assistente_professores postgres-prd -c "
INSERT INTO slot_horario (turno, ordem, horario_inicio, horario_fim)
SELECT DISTINCT
  CASE
    WHEN horario_inicio >= '05:00' AND horario_inicio < '12:00' THEN 'manha'
    WHEN horario_inicio >= '12:00' AND horario_inicio < '18:00' THEN 'tarde'
    WHEN horario_inicio >= '18:00' THEN 'noite'
    ELSE 'madrugada'
  END,
  ROW_NUMBER() OVER (PARTITION BY 
    CASE
      WHEN horario_inicio >= '05:00' AND horario_inicio < '12:00' THEN 'manha'
      WHEN horario_inicio >= '12:00' AND horario_inicio < '18:00' THEN 'tarde'
      WHEN horario_inicio >= '18:00' THEN 'noite'
      ELSE 'madrugada'
    END
    ORDER BY horario_inicio),
  horario_inicio,
  horario_fim
FROM grades
WHERE horario_inicio IS NOT NULL AND horario_fim IS NOT NULL
  AND horario_inicio != '00:00:00'  -- excluir gravações dummy
ON CONFLICT DO NOTHING;
"
```

- [ ] **Step 4: Verificar seeds**

```bash
docker compose exec db psql -U assistente_professores postgres-prd -c "SELECT * FROM estudio ORDER BY id; SELECT * FROM canal_iptv ORDER BY numero; SELECT * FROM slot_horario ORDER BY turno, ordem;"
```

Expected: registros presentes nas três tabelas.

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "seed: dados iniciais de estudio, canal_iptv e slot_horario migrados das grades existentes"
```

---

## Task 12: Teste e Validação End-to-End

- [ ] **Step 1: Testar endpoint de verificação de choque**

```bash
curl -X POST http://localhost:8000/grade/verificar-choque \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dia_semana": 0, "horario_inicio": "07:00", "horario_fim": "08:00", "estudio_id": 1, "canal_iptv_id": 1}'
```

Expected: `{"conflito": false}` se não houver choque, ou `{"conflito": true, "detalhes": {...}}` se houver.

- [ ] **Step 2: Testar listagem de versões de grade**

```bash
curl -X GET "http://localhost:8000/api/v1/turmas/$TURMA_ID/grade-versao" \
  -H "Authorization: Bearer $TOKEN"
```

Expected: array com versões, cada uma contendo `id`, `is_active`, `data_ativacao`, `slots`.

- [ ] **Step 3: Testar CRUD de infraestrutura**

```bash
curl -X GET http://localhost:8000/api/v1/configuracoes/estudios \
  -H "Authorization: Bearer $TOKEN"
curl -X GET http://localhost:8000/api/v1/configuracoes/canais-iptv \
  -H "Authorization: Bearer $TOKEN"
curl -X GET http://localhost:8000/api/v1/configuracoes/slots-horario \
  -H "Authorization: Bearer $TOKEN"
```

Expected: arrays com os dados seedados.

- [ ] **Step 4: Testar live monitor**

Acessar `http://localhost:8000/live-monitor` e confirmar que a matriz carrega sem erros.

- [ ] **Step 5: Testar grade.html**

Acessar `http://localhost:8000/grade`, selecionar uma turma, confirmar que a grade exibe os slots corretamente com os nomes de dias (Segunda, Terça...) ao invés de números.

- [ ] **Step 6: Testar page de configurações**

Acessar `http://localhost:8000/admin/configuracoes`, verificar as três abas (Estúdios, Canais, Slots).

- [ ] **Step 7: Commit final**

```bash
git add .
git commit -m "feat: grade horaria v2 completa - infra, versionamento, choque global, frontend"
```

---

## Checklist de Regressão

Antes de fazer push para HML, verificar:

- [ ] Login funciona normalmente
- [ ] Dashboard carrega sem erros
- [ ] `GET /api/v1/turmas/{id}/grade` ainda retorna dados para turmas existentes
- [ ] `GET /api/v1/live/matrix` retorna dados sem erros
- [ ] `GET /api/v1/cadastros/professores` funciona
- [ ] `GET /api/v1/reports` funciona
- [ ] `POST /api/v1/auth/login` funciona
- [ ] Página `/grade` não tem erros de JS no console
- [ ] Página `/live-monitor` não tem erros de JS no console
- [ ] `/docs` (Swagger) carrega todos os endpoints sem 500

---

## Notas Críticas para Implementação

1. **Transação atômica na ativação**: `PATCH /turmas/{id}/grade-versao/{id}/ativar` desativa a versão anterior e ativa a nova em um único `db.commit()`. Nunca chamar dois commits separados.

2. **Choque é global**: A query de verificação join com `GradeVersao.is_active == True` garante que só compara com grades de versões ativas de qualquer turma.

3. **dia_semana legado**: Grades criadas antes da migration terão `dia_semana` migrado de string para int. O campo `turno_aula` permanece por compatibilidade.

4. **Colunas legadas em `grade`**: `canal_iptv` (int direto), `descricao`, `vigencia_inicio`, `vigencia_fim`, `versao` foram mantidos para não quebrar queries existentes. Novas grades usam `canal_iptv_id` FK.

5. **Alembic**: O migration gerado automaticamente pode incluir detecção de colunas desnecessárias. Revisar o arquivo antes de aplicar — especialmente remover qualquer `drop_table` indevido.
