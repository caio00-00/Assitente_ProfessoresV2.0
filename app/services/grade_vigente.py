"""
Canal Educação v4 — Slots da grade que valem numa data.

Antes do v4 a conferência do relatório de aula buscava os slots da turma só
pelo dia da semana, misturando a versão ativa com versões antigas e rascunhos.
A Agenda e o relatório do diretor já usavam só a versão ativa. Agora todos usam
esta mesma regra:

1. respeita a vigência do slot (vigencia_inicio / vigencia_fim);
2. se a turma tem versão ativa, usa só os slots dela;
3. sem versão ativa, usa os slots legados (sem versão).
"""

from datetime import date
from typing import List
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.auxiliares import Grade
from app.models.infraestrutura import GradeVersao


def slots_da_turma_no_dia(db: Session, turma_id: UUID, data_aula: date) -> List[Grade]:
    if not turma_id or not data_aula:
        return []
    slots = (
        db.query(Grade)
        .filter(
            Grade.turma_id == turma_id,
            Grade.dia_semana == data_aula.weekday(),
            and_(
                or_(Grade.vigencia_inicio <= data_aula, Grade.vigencia_inicio.is_(None)),
                or_(Grade.vigencia_fim >= data_aula, Grade.vigencia_fim.is_(None)),
            ),
        )
        .all()
    )
    ativa = (
        db.query(GradeVersao)
        .filter(GradeVersao.turma_id == turma_id, GradeVersao.is_active == True)  # noqa: E712
        .order_by(GradeVersao.data_ativacao.desc().nullslast())
        .first()
    )
    if ativa:
        return [g for g in slots if g.grade_versao_id == ativa.id]
    return [g for g in slots if g.grade_versao_id is None]
