"""
Conferência da Agenda de Estúdios com o que o sistema já registra.

A agenda é montada da grade; aqui ela é cruzada com os registros reais do dia
(relatórios de aula dos assistentes e relatórios do diretor de imagem) para
apontar o que não bate.
"""

from __future__ import annotations

import re
from datetime import date, time
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.class_report import ClassReport
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import ImageDirectorReport
from app.services.idr_txt_parser import norm_estudio, norm_key


def chave_estudio(nome: Optional[str]) -> str:
    """'Estúdio 03', 'ESTUDIO 3', 'estúdio 03' → 'ESTUDIO 3' (mesma regra dos filtros)."""
    return norm_key(norm_estudio(nome or ""))


def chave_turno(turno: Optional[str]) -> str:
    k = norm_key(turno or "")
    for alvo, valor in (("MANHA", "manha"), ("TARDE", "tarde"), ("NOITE", "noite")):
        if alvo in k:
            return valor
    return ""


def _digitos(txt: Optional[str]) -> str:
    return re.sub(r"\D", "", txt or "")


def _min(t: Optional[time]) -> Optional[int]:
    return t.hour * 60 + t.minute if t else None


def relatorios_de_aula(db: Session, data: date) -> List[ClassReport]:
    return (
        db.query(ClassReport)
        .filter(
            ClassReport.data_aula == data,
            ClassReport.is_deleted == False,  # noqa: E712
            ClassReport.status != "CANCELADO",
        )
        .all()
    )


def casar_relatorios(slots: List[dict], relatorios: List[ClassReport]) -> Tuple[Dict[str, ClassReport], List[ClassReport]]:
    """
    Liga cada aula da grade ao relatório de aula do assistente.
    Mesmo critério da Auditoria: mesma turma + disciplina + horário
    (faixa, início ou "Nº Horário"); na falta, mesma turma + disciplina no dia.
    Retorna (grade_id → relatório, relatórios que não casaram com nenhuma aula).
    """
    livres = list(relatorios)
    casados: Dict[str, ClassReport] = {}

    def mesmo_horario(s: dict, r: ClassReport) -> bool:
        if r.start_time and s["inicio"] and abs(_min(r.start_time) - _min(s["inicio"])) <= 5:
            return True
        faixa = f"{s['inicio'].strftime('%H:%M')} às {s['fim'].strftime('%H:%M')}"
        if _digitos(r.horario_aula) and _digitos(r.horario_aula) == _digitos(faixa):
            return True
        return bool(s.get("ordinal")) and norm_key(r.horario_aula) == norm_key(s["ordinal"])

    for passo in (1, 2):
        for s in slots:
            if s["grade_id"] in casados or s["gravacao_sem_horario"]:
                continue
            for r in livres:
                if str(r.turma_id) != s["turma_id"]:
                    continue
                if str(r.disciplina_id) != str(s["disciplina_id"]):
                    continue
                if passo == 1 and not mesmo_horario(s, r):
                    continue
                casados[s["grade_id"]] = r
                livres.remove(r)
                break
    return casados, livres


def diretores_com_relatorio(db: Session, data: date) -> Dict[Tuple[str, str], List[str]]:
    """(turno, chave do estúdio) → nomes dos diretores que fizeram relatório de imagem no dia."""
    rows = (
        db.query(ImageDirectorReport, DiretorImagem)
        .join(DiretorImagem, ImageDirectorReport.diretor_imagem_id == DiretorImagem.id)
        .filter(
            ImageDirectorReport.data_relatorio == data,
            ImageDirectorReport.is_deleted == False,  # noqa: E712
            ImageDirectorReport.status != "CANCELADO",
        )
        .all()
    )
    saida: Dict[Tuple[str, str], List[str]] = {}
    for idr, diretor in rows:
        chave = (chave_turno(idr.turno), chave_estudio(idr.estudio))
        nomes = saida.setdefault(chave, [])
        if diretor.nome not in nomes:
            nomes.append(diretor.nome)
    return saida


def resumo_relatorio(r: ClassReport) -> dict:
    return {
        "id": str(r.id),
        "status": r.status,
        "estudio": r.estudio,
        "horario": r.horario_aula,
        "precisa_correcao": bool(r.precisa_correcao),
    }
