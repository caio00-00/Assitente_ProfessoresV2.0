"""
Associação entre ImageDirectorReport e ClassReport.

Camada 1 (grade): data, turno, estúdio, turma, disciplina, horário.
Camada 2 (características): youtube, estúdio, diretor de imagem, professor.
"""

from __future__ import annotations

import re
from typing import Optional
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.class_report import ClassReport
from app.models.image_director_report import ImageDirectorReport
from app.services.idr_txt_parser import norm_estudio, norm_turno

TIPOS_ESPECIAIS = ("Gravação estúdio", "Gravação externa", "Manutenção de estúdio")


def _norm_youtube(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return url.strip().rstrip("/").lower()


def _normalize_horario_digits(value: Optional[str]) -> str:
    if not value:
        return ""
    digits = re.sub(r"\D", "", value)
    if digits:
        return digits
    return value.strip().upper()


def _is_gravacao_horario(horario: Optional[str]) -> bool:
    if not horario:
        return False
    h = horario.strip().upper()
    return h in ("GRAVAÇÃO", "GRAVACAO") or "GRAVA" in h


def _is_gravacao_class_report(cr: ClassReport) -> bool:
    return (cr.tipo_aula or "") in TIPOS_ESPECIAIS


def _horarios_compativeis(
    idr_horario: Optional[str],
    cr: ClassReport,
) -> bool:
    cr_horario = cr.horario_aula or ""
    if not idr_horario:
        return True
    if idr_horario == cr_horario:
        return True
    if cr.start_time and cr.end_time:
        faixa = f"{cr.start_time.strftime('%H:%M')} às {cr.end_time.strftime('%H:%M')}"
        if idr_horario == faixa:
            return True
    if _normalize_horario_digits(idr_horario) == _normalize_horario_digits(cr_horario):
        return True
    if _is_gravacao_horario(idr_horario) and _is_gravacao_class_report(cr):
        return True
    return False


def _professor_nome_from_report(report: ImageDirectorReport) -> Optional[str]:
    nome = (report.professor_nome or "").strip()
    if nome and nome != "—":
        return nome
    if report.lessons:
        nome = (report.lessons[0].professor_nome or "").strip()
        return nome or None
    return None


def sync_contexto_from_class_report(report: ImageDirectorReport, cr: ClassReport) -> None:
    """Copia campos de contexto operacional do ClassReport quando vazios no IDR."""
    if not report.disciplina_id and cr.disciplina_id:
        report.disciplina_id = cr.disciplina_id
    if not report.disciplina_nome and cr.disciplina_nome:
        report.disciplina_nome = cr.disciplina_nome
    if not report.professor_id and cr.professor_id:
        report.professor_id = cr.professor_id
    if not report.professor_nome_externo and cr.professor_nome_externo:
        report.professor_nome_externo = cr.professor_nome_externo
    elif not report.professor_id and not report.professor_nome_externo:
        prof = (cr.professor_nome or "").strip()
        if prof and prof != "—":
            report.professor_nome_externo = prof
    if not report.horario_aula and cr.horario_aula:
        report.horario_aula = cr.horario_aula
    if cr.regular:
        report.regular = cr.regular
    if not report.ticket_number and cr.ticket_number:
        report.ticket_number = cr.ticket_number
    if not report.start_time and cr.start_time:
        report.start_time = cr.start_time
    if not report.end_time and cr.end_time:
        report.end_time = cr.end_time
    if not report.turma_id and cr.turma_id:
        report.turma_id = cr.turma_id
    if not report.solicitante_antecipacao and cr.solicitante_antecipacao:
        report.solicitante_antecipacao = cr.solicitante_antecipacao
    if not report.data_referencia and cr.data_referencia_aula:
        report.data_referencia = cr.data_referencia_aula
    if not report.motivo_referencia and cr.motivo_referencia:
        report.motivo_referencia = cr.motivo_referencia


def _match_por_caracteristicas(
    db: Session,
    report: ImageDirectorReport,
    professor_nome: Optional[str] = None,
) -> Optional[ClassReport]:
    """Busca ClassReport por youtube + estúdio + diretor + professor (+ data)."""
    youtube = _norm_youtube(report.youtube_link)
    if not youtube and not report.estudio:
        return None

    prof = professor_nome or _professor_nome_from_report(report)
    q = db.query(ClassReport).filter(
        ClassReport.is_deleted == False,  # noqa: E712
        # reposição: o assistente informa a data da gravação (o diretor registra nesse dia)
        or_(ClassReport.data_aula == report.data_relatorio, ClassReport.data_execucao_real == report.data_relatorio),
    )
    if report.diretor_imagem_id:
        q = q.filter(ClassReport.diretor_imagem_id == report.diretor_imagem_id)
    estudio_ref = norm_estudio(report.estudio)

    for cr in q.all():
        if norm_estudio(cr.estudio) != estudio_ref:
            continue
        if youtube and _norm_youtube(cr.youtube_link) != youtube:
            continue
        if prof:
            cr_prof = (cr.professor_nome or "").strip().lower()
            if cr_prof and cr_prof != prof.strip().lower():
                continue
        return cr
    return None


def _candidatos_por_grade(db: Session, report: ImageDirectorReport) -> list[ClassReport]:
    if report.origem != "grade":
        return []
    if not report.disciplina_id and not report.disciplina_nome:
        return []

    q = db.query(ClassReport).filter(
        ClassReport.is_deleted == False,  # noqa: E712
        # reposição: o assistente informa a data da gravação (o diretor registra nesse dia)
        or_(ClassReport.data_aula == report.data_relatorio, ClassReport.data_execucao_real == report.data_relatorio),
    )
    if report.turma_id:
        q = q.filter(ClassReport.turma_id == report.turma_id)
    if report.disciplina_id:
        q = q.filter(ClassReport.disciplina_id == report.disciplina_id)
    elif report.disciplina_nome:
        q = q.filter(ClassReport.disciplina_nome == report.disciplina_nome)

    # Turno/estúdio comparados normalizados ("Manhã" == "MANHÃ", "Estúdio 1" == "ESTÚDIO 1"):
    # sem isso aulas REGULARES gravadas com grafias diferentes não se associam.
    turno_ref = norm_turno(report.turno)
    estudio_ref = norm_estudio(report.estudio)
    return [
        cr
        for cr in q.all()
        if norm_turno(cr.turno) == turno_ref and norm_estudio(cr.estudio) == estudio_ref
    ]


def _match_por_grade(db: Session, report: ImageDirectorReport) -> Optional[ClassReport]:
    for cr in _candidatos_por_grade(db, report):
        if _is_gravacao_horario(report.horario_aula) or _is_gravacao_class_report(cr):
            if _is_gravacao_class_report(cr):
                return cr
            continue
        if _horarios_compativeis(report.horario_aula, cr):
            return cr
    return None


def associar_class_report(
    db: Session,
    report: ImageDirectorReport,
    class_report_id: Optional[UUID] = None,
) -> Optional[UUID]:
    """Resolve e persiste class_report_id no relatório do diretor."""
    if class_report_id:
        cr = (
            db.query(ClassReport)
            .filter(ClassReport.id == class_report_id, ClassReport.is_deleted == False)  # noqa: E712
            .first()
        )
        if cr:
            report.class_report_id = cr.id
            sync_contexto_from_class_report(report, cr)
            return cr.id

    if report.class_report_id:
        return report.class_report_id

    cr = _match_por_grade(db, report)
    if not cr:
        cr = _match_por_caracteristicas(db, report)
    if cr:
        report.class_report_id = cr.id
        sync_contexto_from_class_report(report, cr)
        return cr.id
    return None


def _datas_do_class_report(cr) -> list:
    """Dia da aula e, se houver, o dia da gravação (reposição gravada depois)."""
    return [d for d in {cr.data_aula, getattr(cr, "data_execucao_real", None)} if d]


def _candidatos_idr_por_class_report(
    db: Session,
    class_report: ClassReport,
) -> list[ImageDirectorReport]:
    q = db.query(ImageDirectorReport).filter(
        ImageDirectorReport.is_deleted == False,  # noqa: E712
        ImageDirectorReport.data_relatorio.in_(_datas_do_class_report(class_report)),
    )
    if class_report.turma_id:
        q = q.filter(ImageDirectorReport.turma_id == class_report.turma_id)
    if class_report.disciplina_id:
        q = q.filter(ImageDirectorReport.disciplina_id == class_report.disciplina_id)
    elif class_report.disciplina_nome:
        q = q.filter(ImageDirectorReport.disciplina_nome == class_report.disciplina_nome)
    # Turno/estúdio comparados normalizados, igual à associação feita pelo lado do diretor
    turno_ref = norm_turno(class_report.turno)
    estudio_ref = norm_estudio(class_report.estudio)
    return [
        idr for idr in q.all()
        if norm_turno(idr.turno) == turno_ref and norm_estudio(idr.estudio) == estudio_ref
    ]


def buscar_image_director_por_class_report(
    db: Session,
    class_report: ClassReport,
) -> Optional[ImageDirectorReport]:
    """Encontra ImageDirectorReport vinculado a um ClassReport."""
    if not class_report:
        return None

    direct = (
        db.query(ImageDirectorReport)
        .filter(
            ImageDirectorReport.class_report_id == class_report.id,
            ImageDirectorReport.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if direct:
        return direct

    for idr in _candidatos_idr_por_class_report(db, class_report):
        if _is_gravacao_class_report(class_report):
            if idr.origem == "grade" or _is_gravacao_horario(idr.horario_aula):
                return idr
            continue
        if _horarios_compativeis(idr.horario_aula, class_report):
            return idr

    youtube = _norm_youtube(class_report.youtube_link)
    if not youtube:
        return None

    estudio_ref = norm_estudio(class_report.estudio)
    candidatos = [
        idr for idr in db.query(ImageDirectorReport).filter(
            ImageDirectorReport.is_deleted == False,  # noqa: E712
            ImageDirectorReport.data_relatorio.in_(_datas_do_class_report(class_report)),
        ).all()
        if norm_estudio(idr.estudio) == estudio_ref
    ]
    prof = (class_report.professor_nome or "").strip().lower()
    for idr in candidatos:
        if _norm_youtube(idr.youtube_link) != youtube:
            continue
        if class_report.diretor_imagem_id and idr.diretor_imagem_id != class_report.diretor_imagem_id:
            continue
        if prof:
            idr_prof = _professor_nome_from_report(idr)
            if idr_prof and idr_prof.strip().lower() != prof:
                continue
        return idr
    return None


def vincular_image_director_ao_class_report(
    db: Session,
    class_report: ClassReport,
) -> Optional[UUID]:
    """Após save/finalize do assistente, relinka relatório de imagem existente."""
    idr = buscar_image_director_por_class_report(db, class_report)
    if idr and idr.class_report_id != class_report.id:
        idr.class_report_id = class_report.id
        sync_contexto_from_class_report(idr, class_report)
    return idr.id if idr else None


def classificar_modalidade_class_report(cr: Optional[ClassReport]) -> Optional[str]:
    """
    Classifica o ClassReport em 'GRAVACAO' ou 'TRANSMISSAO'.
    Retorna None se não for possível classificar.
    """
    if not cr:
        return None
    tipo = (cr.tipo_aula or "").strip().lower()
    if not tipo:
        return None
    if "grava" in tipo:
        return "GRAVACAO"
    return "TRANSMISSAO"


def classificar_modalidade_idr(idr: Optional[ImageDirectorReport]) -> Optional[str]:
    """
    Classifica o ImageDirectorReport em 'GRAVACAO' ou 'TRANSMISSAO'.
    Retorna None se não houver dados suficientes.
    """
    if not idr:
        return None
    # 1. Verifica nas lessons vinculadas
    if idr.lessons:
        tem_transmissao = any(
            (l.transmissao_ou_gravada or "").strip().lower() == "transmissão" or
            (l.transmissao_ou_gravada or "").strip().lower() == "transmissao"
            for l in idr.lessons
        )
        if tem_transmissao:
            return "TRANSMISSAO"
        tem_gravada = any(
            "grava" in (l.transmissao_ou_gravada or "").strip().lower()
            for l in idr.lessons
        )
        if tem_gravada:
            return "GRAVACAO"

    # 2. Verifica horário ou tipo_aula
    tipo_aula = getattr(idr, "tipo_aula", None)
    if tipo_aula:
        if "grava" in tipo_aula.lower():
            return "GRAVACAO"
        if "transmiss" in tipo_aula.lower():
            return "TRANSMISSAO"

    if _is_gravacao_horario(idr.horario_aula):
        return "GRAVACAO"

    return "TRANSMISSAO"


def validar_consistencia_faturamento(
    class_report: Optional[ClassReport],
    idr: Optional[ImageDirectorReport],
) -> None:
    """
    Demanda 1.1 e 138: Trava de consistência obrigatória.
    O tipo de aula no Diretor de Imagem e no Assistente deve ser idêntico:
    Gravação ↔ Gravação ou Transmissão ↔ Transmissão.
    Se divergirem, lança HTTPException 422 impedindo a finalização.
    """
    if not class_report or not idr:
        return

    mod_cr = classificar_modalidade_class_report(class_report)
    mod_idr = classificar_modalidade_idr(idr)

    if mod_cr and mod_idr and mod_cr != mod_idr:
        from fastapi import HTTPException, status
        nome_cr = "Gravação" if mod_cr == "GRAVACAO" else "Transmissão"
        nome_idr = "Gravação" if mod_idr == "GRAVACAO" else "Transmissão"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Inconsistência de faturamento: o tipo de aula deve ser idêntico em ambos os relatórios "
                f"(Assistente de Professores: {nome_cr} ↔ Diretor de Imagem: {nome_idr}). "
                "Ajuste para que ambos sejam Gravação ou ambos sejam Transmissão."
            ),
        )


def gerar_indicativo_reposicao(data_referencia) -> Optional[str]:
    """
    Demanda 1.2: Gera o indicativo textual padronizado de reposição / falta.
    """
    if not data_referencia:
        return None
    try:
        data_str = data_referencia.strftime("%d/%m/%Y")
    except AttributeError:
        data_str = str(data_referencia)
    return f"Gravação por reposição/falta, referente à aula do dia {data_str}"

def gerar_indicativo_antecipada(data_exibicao) -> Optional[str]:
    if not data_exibicao:
        return None
    try:
        data_str = data_exibicao.strftime("%d/%m/%Y")
    except AttributeError:
        data_str = str(data_exibicao)
    return f"Gravação antecipada da aula do dia {data_str}"


def ajustar_datas_gravacao(report) -> None:
    """
    Reunião (out/2026) — relatório do assistente:
    - "Data da aula" (topo do formulário) = a aula na grade (vai no nome do arquivo);
    - "Data da gravação" = o dia em que a aula foi gravada de fato. É ela que define o mês
      do relatório/faturamento quando existe (aula de 30/10 gravada em 03/11 → novembro).
    A data de referência passa a ser automática (= data da aula), sem campo no formulário.
    Registro antigo, só com a data de referência, segue a regra anterior (gravado no dia).
    """
    exec_ = getattr(report, "data_execucao_real", None)
    aula = getattr(report, "data_aula", None)
    if exec_ and aula and exec_ != aula:
        report.data_referencia_aula = aula
        if exec_ > aula:
            report.motivo_referencia = gerar_indicativo_reposicao(aula)
        else:
            report.motivo_referencia = gerar_indicativo_antecipada(aula)
        return
    if exec_ and aula and exec_ == aula and getattr(report, "data_referencia_aula", None) == aula:
        # data da gravação igual à da aula: não é reposição nem antecipada
        report.data_referencia_aula = None
        report.motivo_referencia = None
        return
    ref = getattr(report, "data_referencia_aula", None)
    if ref and not exec_:
        report.data_execucao_real = aula
    if ref and not getattr(report, "motivo_referencia", None):
        report.motivo_referencia = (
            gerar_indicativo_antecipada(ref) if aula and ref > aula else gerar_indicativo_reposicao(ref)
        )


PREFIXO_EXIBICAO = "Exibição da aula gravada antecipadamente em"


def gerar_indicativo_exibicao(data_gravacao) -> Optional[str]:
    """Reunião (out/2026): a exibição de uma aula antecipada aponta para o dia da gravação."""
    if not data_gravacao:
        return None
    try:
        data_str = data_gravacao.strftime("%d/%m/%Y")
    except AttributeError:
        data_str = str(data_gravacao)
    return f"{PREFIXO_EXIBICAO} {data_str}"


def divergencias_do_par(cr: ClassReport, idr: ImageDirectorReport) -> list[str]:
    """
    O que não bate entre o relatório do assistente e o do diretor de imagem ligados
    à mesma aula. Usado como aviso na validação (não bloqueia).
    """
    msgs: list[str] = []
    if cr.data_aula and idr.data_relatorio and idr.data_relatorio not in _datas_do_class_report(cr):
        msgs.append(f"Data: assistente {cr.data_aula:%d/%m/%Y}, diretor {idr.data_relatorio:%d/%m/%Y}.")
    if norm_estudio(cr.estudio) != norm_estudio(idr.estudio):
        msgs.append(f"Estúdio: assistente {cr.estudio or '—'}, diretor {idr.estudio or '—'}.")
    if norm_turno(cr.turno) != norm_turno(idr.turno):
        msgs.append(f"Turno: assistente {cr.turno or '—'}, diretor {idr.turno or '—'}.")
    if cr.turma_id and idr.turma_id and cr.turma_id != idr.turma_id:
        msgs.append("Turma diferente nos dois relatórios.")
    if cr.disciplina_id and idr.disciplina_id and cr.disciplina_id != idr.disciplina_id:
        msgs.append("Disciplina diferente nos dois relatórios.")
    if idr.horario_aula and not _is_gravacao_class_report(cr):
        mesmo_inicio = bool(cr.start_time and idr.start_time and cr.start_time == idr.start_time)
        if not mesmo_inicio and not _horarios_compativeis(idr.horario_aula, cr):
            msgs.append(f"Horário: assistente {cr.horario_aula or '—'}, diretor {idr.horario_aula}.")
    return msgs
