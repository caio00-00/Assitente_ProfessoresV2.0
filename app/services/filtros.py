"""
Helpers de filtragem compartilhados (Auditoria, Histórico do Diretor de Imagem,
exportação Excel e estatísticas).

Os valores gravados no banco nem sempre têm a mesma grafia do filtro
("ESTÚDIO 3", "Estúdio 03", "estudio 3"; "Manhã"/"MANHÃ") e professores podem
estar duplicados com o mesmo nome. Estes helpers traduzem o valor escolhido no
filtro para TODAS as variantes equivalentes, para o filtro não "sumir" com
registros.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.auxiliares import Disciplina, Professor
from app.services.idr_txt_parser import norm_estudio, norm_key


def validar_periodo(data_inicio: Optional[date], data_fim: Optional[date]) -> None:
    if data_inicio and data_fim and data_inicio > data_fim:
        raise HTTPException(
            status_code=422,
            detail="A data de início não pode ser maior que a data de fim.",
        )


def estudio_variantes(db: Session, coluna, estudio: str) -> List[str]:
    """Valores distintos da coluna que representam o mesmo estúdio do filtro."""
    alvo = norm_estudio(estudio)
    alvo_key = norm_key(alvo)
    valores = [v for (v,) in db.query(coluna).distinct().all() if v]
    variantes = [v for v in valores if norm_key(norm_estudio(v)) == alvo_key]
    return variantes or [estudio]


def valores_equivalentes(db: Session, coluna, texto: Optional[str]) -> List[str]:
    """
    Valores distintos gravados na coluna que equivalem ao texto ignorando
    acentos, caixa e espaços extras ("João Silva" = "JOAO  SILVA").
    """
    alvo = norm_key(texto)
    if not alvo:
        return []
    valores = [v for (v,) in db.query(coluna).distinct().all() if v]
    return [v for v in valores if norm_key(v) == alvo]


def professor_equivalentes(db: Session, professor_id: UUID) -> Tuple[List[UUID], Optional[str]]:
    """
    IDs de todos os cadastros de professor com o MESMO nome (duplicatas) e o nome.
    O dropdown de filtro mostra um nome só (DISTINCT), mas os relatórios podem
    estar ligados a qualquer um dos cadastros duplicados.
    """
    prof = db.query(Professor).filter(Professor.id == professor_id).first()
    if not prof:
        return [professor_id], None
    nome_key = norm_key(prof.nome)
    ids = [p.id for p in db.query(Professor).all() if norm_key(p.nome) == nome_key] or [professor_id]
    return ids, prof.nome


def disciplina_equivalentes(db: Session, disciplina_id: UUID) -> Tuple[List[UUID], Optional[str]]:
    """IDs de disciplinas com o mesmo nome normalizado (cadastros duplicados)."""
    disc = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
    if not disc:
        return [disciplina_id], None
    nome_key = norm_key(disc.nome)
    ids = [d.id for d in db.query(Disciplina).all() if norm_key(d.nome) == nome_key]
    return ids or [disciplina_id], disc.nome
