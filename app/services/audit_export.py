"""
Exportação Excel do painel de auditoria — 3 abas:
Consolidado, Assistente e Diretor Imagem.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy.orm import Session, joinedload

from app.models.auxiliares import Disciplina, Professor
from app.models.class_report import ClassReport
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import (
    ImageDirectorChecklistItem,
    ImageDirectorCustomQuestion,
    ImageDirectorLesson,
    ImageDirectorReport,
)
from app.models.turma import Turma
from app.services.idr_txt_parser import norm_estudio
from app.services.image_director_associacao import (
    _horarios_compativeis,
    _norm_youtube,
    _professor_nome_from_report,
)

DIAS_PT = {
    0: "Segunda",
    1: "Terça",
    2: "Quarta",
    3: "Quinta",
    4: "Sexta",
    5: "Sábado",
    6: "Domingo",
}

STATUS_LABELS = {
    "RASCUNHO": "Rascunho",
    "AGUARDANDO_VALIDACAO": "Aguardando Validação",
    "VALIDADO": "Validado",
    "CANCELADO": "Cancelado",
    "FINALIZADO": "Finalizado (legado)",
}

HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT = Font(bold=True, size=10, color="FFFFFF")
FAT_HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# Caracteres de controle proibidos em XML/Excel (openpyxl IllegalCharacterError)
_ILLEGAL_XML_CHARS = re.compile(r"[\000-\010]|[\013-\014]|[\016-\037]")


@dataclass
class AuditExportFilters:
    data_aula: Optional[date] = None
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    turma_id: Optional[UUID] = None
    professor_id: Optional[UUID] = None
    disciplina_id: Optional[UUID] = None
    status_filter: Optional[str] = None
    estudio: Optional[str] = None
    tipo_aula: Optional[str] = None
    com_atraso: Optional[bool] = None
    com_substituicao: Optional[bool] = None
    com_problema: Optional[bool] = None
    precisa_correcao: Optional[bool] = None
    created_by: Optional[UUID] = None
    modalidade_aula: Optional[str] = None
    status_idr: Optional[str] = None


def _sanitize_excel_value(value: Any) -> Any:
    """Remove caracteres de controle que o openpyxl rejeita (ex.: \\x0b)."""
    if value is None:
        return None
    if isinstance(value, (int, float, bool, datetime, date)):
        return value
    text = str(value)
    return _ILLEGAL_XML_CHARS.sub("", text)


def format_problematic_materials(materials: Any) -> str:
    if not materials:
        return ""
    if isinstance(materials, str):
        return _sanitize_excel_value(materials.strip())
    if not isinstance(materials, (list, tuple)):
        return str(materials)
    parts = []
    for item in materials:
        if isinstance(item, dict):
            mat = item.get("material") or item.get("nome") or ""
            desc = item.get("descricao") or item.get("description") or ""
            if mat or desc:
                parts.append(f"[{mat}]: {desc}".strip())
        else:
            parts.append(str(item))
    return _sanitize_excel_value("; ".join(parts))


def _safe_join_values(value: Any, sep: str = ", ") -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set)):
        return sep.join(str(v) for v in value if v is not None and str(v).strip())
    return str(value)


def _has_recursos_utilizados(value: Any) -> bool:
    if not value:
        return False
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _fmt_bool(value: Optional[bool]) -> str:
    if value is True:
        return "Sim"
    if value is False:
        return "Não"
    return ""


def _fmt_time(value: Any) -> str:
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M:%S")
    return str(value)


def _fmt_datetime(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value)


def _status_label(status: Optional[str], precisa_correcao: bool = False) -> str:
    label = STATUS_LABELS.get(status or "", status or "")
    if precisa_correcao:
        label += " (Correção solicitada)"
    return label


def _safe_col_name(prefix: str, text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text or "", flags=re.UNICODE)
    slug = re.sub(r"\s+", "_", slug.strip())[:40]
    return f"{prefix}_{slug or 'item'}"


def _write_header(ws: Worksheet, headers: List[str], fill: PatternFill = HEADER_FILL) -> None:
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=_sanitize_excel_value(header))
        cell.font = HEADER_FONT
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER


def _write_row(ws: Worksheet, row_idx: int, values: List[Any]) -> None:
    for col_idx, value in enumerate(values, 1):
        cell = ws.cell(row=row_idx, column=col_idx, value=_sanitize_excel_value(value))
        cell.border = THIN_BORDER
        cell.alignment = Alignment(vertical="center")


def _autosize_columns(ws: Worksheet, num_cols: int, num_rows: int) -> None:
    for col_idx in range(1, num_cols + 1):
        max_len = len(str(ws.cell(row=1, column=col_idx).value or ""))
        for row in range(2, min(num_rows + 2, 52)):
            max_len = max(max_len, len(str(ws.cell(row=row, column=col_idx).value or "")))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_len + 2, 12), 40)


def _apply_idr_export_filters(query, filters: AuditExportFilters, db: Optional[Session] = None):
    query = query.filter(ImageDirectorReport.is_deleted == False)  # noqa: E712
    if filters.data_aula:
        query = query.filter(ImageDirectorReport.data_relatorio == filters.data_aula)
    if filters.data_inicio:
        query = query.filter(ImageDirectorReport.data_relatorio >= filters.data_inicio)
    if filters.data_fim:
        query = query.filter(ImageDirectorReport.data_relatorio <= filters.data_fim)
    if filters.turma_id:
        query = query.filter(ImageDirectorReport.turma_id == filters.turma_id)
    if filters.professor_id and db is not None:
        from app.api.rotas_diretor_imagem import _filtrar_idr_professor

        query = _filtrar_idr_professor(db, query, filters.professor_id)
    elif filters.professor_id:
        query = query.filter(ImageDirectorReport.professor_id == filters.professor_id)
    if filters.disciplina_id and db is not None:
        from app.api.rotas_diretor_imagem import _filtrar_idr_disciplina

        query = _filtrar_idr_disciplina(db, query, filters.disciplina_id)
    elif filters.disciplina_id:
        query = query.filter(ImageDirectorReport.disciplina_id == filters.disciplina_id)
    if filters.status_filter:
        query = query.filter(ImageDirectorReport.status == filters.status_filter.strip().upper())
    if filters.estudio:
        if db is not None:
            from app.services.filtros import estudio_variantes

            query = query.filter(
                ImageDirectorReport.estudio.in_(estudio_variantes(db, ImageDirectorReport.estudio, filters.estudio))
            )
        else:
            query = query.filter(ImageDirectorReport.estudio == filters.estudio)
    if filters.precisa_correcao is not None:
        query = query.filter(ImageDirectorReport.precisa_correcao == filters.precisa_correcao)
    if filters.status_idr:
        st = filters.status_idr.strip().upper()
        if st == "SEM_RELATORIO":
            from sqlalchemy import false

            query = query.filter(false())  # sem relatório do diretor → aba do diretor vazia
        else:
            query = query.filter(ImageDirectorReport.status == st)
    if filters.modalidade_aula:
        tipo_lesson = "Aula gravada" if filters.modalidade_aula.strip().lower() == "gravacao" else "Transmissão"
        from sqlalchemy import select

        com_tipo = select(ImageDirectorLesson.report_id).where(
            ImageDirectorLesson.transmissao_ou_gravada == tipo_lesson
        )
        query = query.filter(ImageDirectorReport.id.in_(com_tipo))
    return query


def _load_class_reports(db: Session, filters: AuditExportFilters) -> List[ClassReport]:
    from app.api.rotas_report import _apply_report_filters

    query = db.query(ClassReport)
    query = _apply_report_filters(
        query,
        db=db,
        data_aula=filters.data_aula,
        data_inicio=filters.data_inicio,
        data_fim=filters.data_fim,
        turma_id=filters.turma_id,
        professor_id=filters.professor_id,
        disciplina_id=filters.disciplina_id,
        status_filter=filters.status_filter,
        estudio=filters.estudio,
        tipo_aula=filters.tipo_aula,
        com_atraso=filters.com_atraso,
        com_substituicao=filters.com_substituicao,
        com_problema=filters.com_problema,
        created_by=filters.created_by,
        precisa_correcao=filters.precisa_correcao,
        modalidade_aula=filters.modalidade_aula,
        status_idr=filters.status_idr,
        periodo_por_gravacao=True,
    )
    return query.order_by(ClassReport.data_aula.desc(), ClassReport.created_at.desc()).all()


def _load_idr_reports(db: Session, filters: AuditExportFilters) -> List[ImageDirectorReport]:
    query = db.query(ImageDirectorReport).options(
        joinedload(ImageDirectorReport.lessons).joinedload(ImageDirectorLesson.respostas_extras),
        joinedload(ImageDirectorReport.checklist_respostas),
        joinedload(ImageDirectorReport.respostas_extras),
        joinedload(ImageDirectorReport.diretor_imagem),
        joinedload(ImageDirectorReport.turma),
        joinedload(ImageDirectorReport.disciplina),
        joinedload(ImageDirectorReport.professor),
        joinedload(ImageDirectorReport.validador),
        joinedload(ImageDirectorReport.creator),
    )
    query = _apply_idr_export_filters(query, filters, db)
    return query.order_by(
        ImageDirectorReport.data_relatorio.desc(),
        ImageDirectorReport.created_at.desc(),
    ).all()


def _load_lookup_maps(
    db: Session,
    class_reports: List[ClassReport],
    idr_reports: List[ImageDirectorReport],
) -> Tuple[Dict, Dict, Dict, Dict]:
    turma_ids = {r.turma_id for r in class_reports if r.turma_id}
    turma_ids |= {r.turma_id for r in idr_reports if r.turma_id}
    disc_ids = {r.disciplina_id for r in class_reports if r.disciplina_id}
    disc_ids |= {r.disciplina_id for r in idr_reports if r.disciplina_id}
    prof_ids = {r.professor_id for r in class_reports if r.professor_id}
    prof_ids |= {r.professor_substituto_id for r in class_reports if r.professor_substituto_id}
    prof_ids |= {r.professor_id for r in idr_reports if r.professor_id}
    dir_ids = {r.diretor_imagem_id for r in class_reports if r.diretor_imagem_id}
    dir_ids |= {r.diretor_imagem_id for r in idr_reports if r.diretor_imagem_id}

    turmas_map = (
        {t.id: t for t in db.query(Turma).filter(Turma.id.in_(turma_ids)).all()}
        if turma_ids
        else {}
    )
    discs_map = (
        {d.id: d for d in db.query(Disciplina).filter(Disciplina.id.in_(disc_ids)).all()}
        if disc_ids
        else {}
    )
    profs_map = (
        {p.id: p for p in db.query(Professor).filter(Professor.id.in_(prof_ids)).all()}
        if prof_ids
        else {}
    )
    dir_map = (
        {d.id: d for d in db.query(DiretorImagem).filter(DiretorImagem.id.in_(dir_ids)).all()}
        if dir_ids
        else {}
    )
    return turmas_map, discs_map, profs_map, dir_map


def _class_horario_str(report: ClassReport, turma: Optional[Turma]) -> str:
    from app.api.rotas_report import _resolver_horario

    if report.start_time and report.end_time:
        return f"{report.start_time.strftime('%H:%M:%S')} - {report.end_time.strftime('%H:%M:%S')}"
    st_fb, et_fb = _resolver_horario(
        report.horario_aula,
        turma.nomenclatura_padrao if turma else "",
        turno_usuario=report.turno or "",
    )
    if st_fb and et_fb:
        return f"{st_fb.strftime('%H:%M:%S')} - {et_fb.strftime('%H:%M:%S')}"
    return report.horario_aula or ""


def _idr_horario_str(report: ImageDirectorReport) -> str:
    if report.start_time and report.end_time:
        return f"{report.start_time.strftime('%H:%M:%S')} - {report.end_time.strftime('%H:%M:%S')}"
    return report.horario_aula or ""


def _professor_name_class(
    report: ClassReport,
    profs_map: Dict,
) -> str:
    prof = profs_map.get(report.professor_id) if report.professor_id else None
    return prof.nome if prof else (report.professor_nome_externo or "")


def _match_idr_for_class(
    cr: ClassReport,
    idrs: List[ImageDirectorReport],
    used: Set[UUID],
) -> Optional[ImageDirectorReport]:
    for idr in idrs:
        if idr.id in used:
            continue
        if idr.class_report_id == cr.id:
            return idr

    for idr in idrs:
        if idr.id in used or idr.class_report_id:
            continue
        # estúdio comparado normalizado ("Estúdio 04" = "ESTÚDIO 4")
        # reposição: o diretor registra no dia da gravação (data da gravação do assistente)
        datas_cr = {cr.data_aula, getattr(cr, "data_execucao_real", None)}
        if idr.data_relatorio not in datas_cr or norm_estudio(idr.estudio) != norm_estudio(cr.estudio):
            continue
        if idr.turma_id and cr.turma_id and idr.turma_id != cr.turma_id:
            continue
        if idr.disciplina_id and cr.disciplina_id and idr.disciplina_id != cr.disciplina_id:
            continue
        if not _horarios_compativeis(idr.horario_aula, cr):
            continue
        return idr

    youtube = _norm_youtube(cr.youtube_link)
    if youtube:
        prof = (cr.professor_nome or "").strip().lower()
        for idr in idrs:
            if idr.id in used:
                continue
            if _norm_youtube(idr.youtube_link) != youtube:
                continue
            if cr.diretor_imagem_id and idr.diretor_imagem_id != cr.diretor_imagem_id:
                continue
            idr_prof = (_professor_nome_from_report(idr) or "").strip().lower()
            if prof and idr_prof and idr_prof != prof:
                continue
            return idr
    return None


def _build_pairings(
    class_reports: List[ClassReport],
    idr_reports: List[ImageDirectorReport],
) -> Tuple[List[Tuple[Optional[ClassReport], Optional[ImageDirectorReport]]], Dict[UUID, Optional[UUID]]]:
    """Retorna linhas consolidadas e mapa class_id -> idr_id para aba Assistente."""
    used_idr: Set[UUID] = set()
    rows: List[Tuple[Optional[ClassReport], Optional[ImageDirectorReport]]] = []
    class_to_idr: Dict[UUID, Optional[UUID]] = {}

    for cr in class_reports:
        idr = _match_idr_for_class(cr, idr_reports, used_idr)
        if idr:
            used_idr.add(idr.id)
            class_to_idr[cr.id] = idr.id
        else:
            class_to_idr[cr.id] = None
        rows.append((cr, idr))

    for idr in idr_reports:
        if idr.id not in used_idr:
            rows.append((None, idr))

    def sort_key(item):
        cr, idr = item
        ref = cr or idr
        data = ((getattr(cr, "data_execucao_real", None) or cr.data_aula) if cr else idr.data_relatorio)
        turno = (cr.turno if cr else idr.turno) or ""
        estudio = (cr.estudio if cr else idr.estudio) or ""
        horario = (cr.horario_aula if cr else idr.horario_aula) or ""
        return (data or date.min, turno, estudio, horario)

    rows.sort(key=sort_key, reverse=True)
    return rows, class_to_idr


def _idr_lesson_flags(idr: Optional[ImageDirectorReport]) -> Tuple[str, str, str]:
    if not idr or not idr.lessons:
        return "", "", ""
    lesson = idr.lessons[0]
    return lesson.video_corrompido or "", lesson.problema_audio or "", lesson.interrupcoes or ""


def classificar_lancamento(
    cr: Optional[ClassReport], idr: Optional[ImageDirectorReport]
) -> Tuple[str, str]:
    """
    Reunião (out/2026) — regra de cobrança:
    - a EXIBIÇÃO é sempre cobrada (inclusive a de aula gravada antes e a reposição);
    - a GRAVAÇÃO ANTECIPADA só é cobrada quando o pedido é da SEDUC (cobra 2x: gravação + exibição);
      pedido do Canal Educação/professor cobra 1x, só na exibição.
    Retorna (lançamento, cobrar).
    """
    from app.services.image_director_associacao import PREFIXO_EXIBICAO

    motivo = (
        (getattr(cr, "motivo_referencia", None) if cr else None)
        or (getattr(idr, "motivo_referencia", None) if idr else None)
        or ""
    )
    if motivo.startswith(PREFIXO_EXIBICAO):
        return "EXIBIÇÃO DE AULA ANTECIPADA", "Sim"
    solicitante = (
        (getattr(cr, "solicitante_antecipacao", None) if cr else None)
        or (getattr(idr, "solicitante_antecipacao", None) if idr else None)
        or ""
    )
    execucao = (
        (getattr(cr, "data_execucao_real", None) or getattr(cr, "data_aula", None)) if cr
        else getattr(idr, "data_relatorio", None)
    )
    referencia = (
        (getattr(cr, "data_referencia_aula", None) if cr else None)
        or (getattr(idr, "data_referencia", None) if idr else None)
    )
    if execucao and referencia and referencia > execucao:
        if solicitante == "SEDUC":
            return "GRAVAÇÃO ANTECIPADA", "Sim"
        return "GRAVAÇÃO ANTECIPADA", "Não (cobra só a exibição)"
    if execucao and referencia and referencia < execucao:
        return "REPOSIÇÃO", "Sim"
    return "AULA", "Sim"


def cobrar_conforme_status(
    cr: Optional[ClassReport], idr: Optional[ImageDirectorReport], cobrar: str
) -> str:
    """
    v4: o COBRAR da regra só vale quando os relatórios da aula estão validados.
    Antes um rascunho ou um cancelado saía com "Sim" na planilha da SEDUC.
    - algum cancelado → "Não (cancelado)"
    - algum ainda não validado → "Pendente (…)" dizendo qual falta
    - todos os existentes validados → o COBRAR da regra (Sim / Não …)
    """
    relatorios = [("assistente", cr), ("diretor", idr)]
    if any(r is not None and (r.status or "") == "CANCELADO" for _, r in relatorios):
        return "Não (cancelado)"
    faltam = [quem for quem, r in relatorios if r is not None and (r.status or "") != "VALIDADO"]
    if faltam:
        return f"Pendente (falta validar: {' e '.join(faltam)})"
    return cobrar


def _sheet_faturamento_seduc(
    ws: Worksheet,
    pairings: List[Tuple[Optional[ClassReport], Optional[ImageDirectorReport]]],
    turmas_map: Dict,
    discs_map: Dict,
    profs_map: Dict,
    dir_map: Dict,
    is_coord: bool = False,
) -> None:
    headers = [
        "DATA_EXECUÇÃO_REAL",
        "MÊS_EXECUÇÃO",
        "DATA_REFERÊNCIA",
        "MÊS_REFERÊNCIA",
        "INDICATIVO_REPOSIÇÃO",
        "MODALIDADE",
        "ESTÚDIO",
        "TURNO",
        "CURSO_TURMA",
        "DISCIPLINA",
        "PROFESSOR",
    ]
    if not is_coord:
        headers.append("DIRETOR_IMAGEM")
    headers.extend([
        "É_ANTECIPAÇÃO",
        "SOLICITANTE_ANTECIPAÇÃO",
        "Nº_CHAMADO_SEDUC",
        "COBRANÇA_SEDUC",
        "LANÇAMENTO",
        "COBRAR",
        "VALOR_FATURÁVEL",
        "STATUS_ASSISTENTE",
    ])
    if not is_coord:
        headers.extend([
            "STATUS_DIR_IMAGEM",
            "CONGRUÊNCIA_MODALIDADE",
        ])
    _write_header(ws, headers, fill=FAT_HEADER_FILL)

    for row_idx, (cr, idr) in enumerate(pairings, 2):
        data_exec = (
            getattr(cr, "data_execucao_real", None)
            if cr and getattr(cr, "data_execucao_real", None)
            # v4: o relatório do diretor não tem data_execucao_real; a data em que ele
            # trabalhou é data_relatorio (antes lia um campo inexistente)
            else (idr.data_relatorio if idr else None)
        )
        data_ref = (
            getattr(cr, "data_referencia_aula", None)
            if cr and getattr(cr, "data_referencia_aula", None)
            # v4: no relatório do diretor o campo se chama data_referencia
            else (getattr(idr, "data_referencia", None) if idr and getattr(idr, "data_referencia", None)
                  else (cr.data_aula if cr else getattr(idr, "data_relatorio", None)))
        )
        mes_exec = data_exec.strftime("%m/%Y") if data_exec else ""
        mes_ref = data_ref.strftime("%m/%Y") if data_ref else ""
        indicativo = (
            (getattr(cr, "motivo_referencia", None) if cr else None)
            or (getattr(idr, "motivo_referencia", None) if idr else None)
            or ""
        )
        if not indicativo and data_ref and data_exec and (data_ref != data_exec):
            from app.services.image_director_associacao import gerar_indicativo_reposicao
            indicativo = gerar_indicativo_reposicao(data_ref)

        from app.services.image_director_associacao import (
            classificar_modalidade_class_report,
            classificar_modalidade_idr,
        )

        mod_cr = classificar_modalidade_class_report(cr) if cr else ""
        mod_idr = classificar_modalidade_idr(idr) if idr else ""
        modalidade = mod_cr or mod_idr or "GRAVACAO"
        congruencia = "OK" if (not cr or not idr or mod_cr == mod_idr) else f"DIVERGENTE ({mod_cr} vs {mod_idr})"

        turma = turmas_map.get(cr.turma_id if cr else idr.turma_id)
        disc = discs_map.get(cr.disciplina_id if cr else idr.disciplina_id)
        prof_name = _professor_name_class(cr, profs_map) if cr else (idr.professor_nome if idr else "")
        if idr and not prof_name:
            prof_name = _professor_nome_from_report(idr) or ""

        diretor = (
            dir_map.get(idr.diretor_imagem_id).nome
            if idr and idr.diretor_imagem_id in dir_map
            else (dir_map.get(cr.diretor_imagem_id).nome if cr and cr.diretor_imagem_id in dir_map else "")
        )

        solicitante = (
            getattr(cr, "solicitante_antecipacao", None)
            if cr and getattr(cr, "solicitante_antecipacao", None)
            else (getattr(idr, "solicitante_antecipacao", "") if idr else "")
        )
        lancamento, cobrar_regra = classificar_lancamento(cr, idr)
        # v4: antes lia "is_antecipacao", campo que não existe; agora vem do lançamento
        is_antec = "Sim" if (lancamento in ("GRAVAÇÃO ANTECIPADA", "EXIBIÇÃO DE AULA ANTECIPADA") or bool(solicitante)) else "Não"
        chamado = (getattr(cr, "ticket_number", None) if cr else None) or (getattr(idr, "ticket_number", None) if idr else "") or ""
        # v4: tipo_cobranca_seduc e valor_faturavel nunca existiram no banco. A cobrança
        # sai do pedido SEDUC; o valor fica em branco (não há tabela de preços no sistema)
        cobranca = "DUPLA" if (solicitante or "").upper() == "SEDUC" else "SIMPLES"

        values = [
            data_exec.strftime("%d/%m/%Y") if data_exec else "",
            mes_exec,
            data_ref.strftime("%d/%m/%Y") if data_ref else "",
            mes_ref,
            indicativo,
            modalidade,
            (cr.estudio if cr else idr.estudio) or "",
            (cr.turno if cr else idr.turno) or "",
            turma.nome if turma else (idr.turma_nome if idr else ""),
            disc.nome if disc else (idr.disciplina_nome if idr else ""),
            prof_name,
        ]
        if not is_coord:
            values.append(diretor)
        values.extend([
            is_antec,
            solicitante,
            chamado,
            cobranca,
            lancamento,
            cobrar_conforme_status(cr, idr, cobrar_regra),
            "",  # VALOR_FATURÁVEL: sem tabela de preços no sistema (antes saía sempre R$ 0,00)
            _status_label(cr.status, cr.precisa_correcao) if cr else "",
        ])
        if not is_coord:
            values.extend([
                _status_label(idr.status, idr.precisa_correcao) if idr else "",
                congruencia,
            ])
        _write_row(ws, row_idx, values)

    _autosize_columns(ws, len(headers), len(pairings))


def _sheet_consolidado(
    target: Any,
    pairings: List[Tuple[Optional[ClassReport], Optional[ImageDirectorReport]]],
    turmas_map: Dict,
    discs_map: Dict,
    profs_map: Dict,
    dir_map: Dict,
    is_coord: bool = False,
) -> None:
    if isinstance(target, Workbook):
        ws = target.active if "Consolidado" not in target.sheetnames else target["Consolidado"]
        ws.title = "Consolidado"
    else:
        ws = target

    headers = [
        "DATA",
        "DIA",
        "TURNO",
        "ESTÚDIO",
        "CURSO",
        "HORÁRIO",
        "DISCIPLINA",
        "PROFESSOR",
        "ID_RELATORIO_ASSISTENTE",
    ]
    if not is_coord:
        headers.extend(["ID_RELATORIO_IMAGEM", "VINCULADO", "ORIGEM_IDR"])
    headers.extend([
        "STATUS_ASSISTENTE",
        "STATUS_COMPLIANCE",
        "YOUTUBE_ASSISTENTE",
        "LINK_VÍDEO",
        "LINK_VIMEO",
        "LINK_SLIDE",
        "FICHEIRO_GERADO",
    ])
    if not is_coord:
        headers.extend([
            "DIRETOR_IMAGEM",
            "STATUS_IMAGEM",
            "YOUTUBE_IMAGEM",
            "HORÁRIO_ENTRADA",
            "HORÁRIO_SAÍDA",
            "VALIDADO_ASSISTENTE_POR",
            "VALIDADO_IMAGEM_POR",
            "CORREÇÃO_PENDENTE_ASSISTENTE",
            "CORREÇÃO_PENDENTE_IMAGEM",
        ])
    else:
        headers.extend([
            "VALIDADO_ASSISTENTE_POR",
            "CORREÇÃO_PENDENTE_ASSISTENTE",
        ])
    headers.extend([
        "TEM_ATRASO",
        "TEM_SUBSTITUIÇÃO",
        "PROBLEMA_MATERIAL",
    ])
    if not is_coord:
        headers.extend([
            "IDR_VÍDEO_CORROMPIDO",
            "IDR_PROBLEMA_ÁUDIO",
            "IDR_INTERRUPÇÕES",
        ])
    headers.extend([
        "DATA_EXECUÇÃO_REAL",
        "DATA_REFERÊNCIA",
        "INDICATIVO_REPOSIÇÃO",
        "SOLICITANTE_ANTECIPAÇÃO",
        "CHAMADO_SEDUC",
        "TIPO_COBRANÇA_SEDUC",
    ])
    _write_header(ws, headers)

    for row_idx, (cr, idr) in enumerate(pairings, 2):
        ref_data = cr.data_aula if cr else idr.data_relatorio
        turma = turmas_map.get(cr.turma_id if cr else idr.turma_id)
        disc = discs_map.get(cr.disciplina_id if cr else idr.disciplina_id)
        prof_name = _professor_name_class(cr, profs_map) if cr else (idr.professor_nome if idr else "")
        if idr and not prof_name:
            prof_name = _professor_nome_from_report(idr) or ""

        horario = _class_horario_str(cr, turma) if cr else _idr_horario_str(idr)
        disciplina = disc.nome if disc else (idr.disciplina_nome if idr else "")
        vinculado = "Sim" if cr and idr else "Não"
        vid_cor, aud, inter = _idr_lesson_flags(idr)
        diretor = (
            dir_map.get(idr.diretor_imagem_id).nome
            if idr and idr.diretor_imagem_id in dir_map
            else (dir_map.get(cr.diretor_imagem_id).nome if cr and cr.diretor_imagem_id in dir_map else "")
        )

        values = [
            ref_data.strftime("%d/%m/%Y") if ref_data else "",
            DIAS_PT.get(ref_data.weekday(), "") if ref_data else "",
            (cr.turno if cr else idr.turno) or "",
            (cr.estudio if cr else idr.estudio) or "",
            turma.nome if turma else (idr.turma_nome if idr else ""),
            horario,
            disciplina,
            prof_name,
            str(cr.id) if cr else "",
        ]
        if not is_coord:
            values.extend([
                str(idr.id) if idr else "",
                vinculado,
                idr.origem if idr else "",
            ])
        values.extend([
            _status_label(cr.status, cr.precisa_correcao) if cr else "",
            cr.status_compliance if cr else "",
            cr.youtube_link if cr else "",
            cr.video_link if cr else "",
            cr.vimeo_link if cr else "",
            cr.slide_link if cr else "",
            cr.nome_ficheiro_gerado if cr else "",
        ])
        if not is_coord:
            values.extend([
                diretor,
                _status_label(idr.status, idr.precisa_correcao) if idr else "",
                idr.youtube_link if idr else "",
                _fmt_time(idr.horario_entrada) if idr else "",
                _fmt_time(idr.horario_saida) if idr else "",
                cr.validado_por_nome if cr else "",
                idr.validado_por_nome if idr else "",
                "Sim" if cr and cr.precisa_correcao else "Não",
                "Sim" if idr and idr.precisa_correcao else "Não",
            ])
        else:
            values.extend([
                cr.validado_por_nome if cr else "",
                "Sim" if cr and cr.precisa_correcao else "Não",
            ])
        values.extend([
            "Sim" if cr and cr.teve_atraso else "Não",
            "Sim" if cr and cr.teve_substituicao else "Não",
            "Sim" if cr and cr.problema_material and cr.problema_material != "Não" else "Não",
        ])
        if not is_coord:
            values.extend([
                vid_cor,
                aud,
                inter,
            ])
        data_exec = (
            getattr(cr, "data_execucao_real", None)
            if cr and getattr(cr, "data_execucao_real", None)
            else None  # v4: o relatório do diretor não tem data de execução própria
        )
        data_ref = (
            getattr(cr, "data_referencia_aula", None)
            if cr and getattr(cr, "data_referencia_aula", None)
            # v4: no relatório do diretor o campo se chama data_referencia
            else (getattr(idr, "data_referencia", None) if idr else None)
        )
        indicativo = (
            (getattr(cr, "motivo_referencia", None) if cr else None)
            or (getattr(idr, "motivo_referencia", None) if idr else None)
            or ""
        )
        solicitante = (
            getattr(cr, "solicitante_antecipacao", None)
            if cr and getattr(cr, "solicitante_antecipacao", None)
            else (getattr(idr, "solicitante_antecipacao", "") if idr else "")
        )
        chamado = (getattr(cr, "ticket_number", None) if cr else None) or (getattr(idr, "ticket_number", None) if idr else "") or ""
        # v4: tipo_cobranca_seduc não existe no banco; deduzido do pedido SEDUC
        cobranca = "DUPLA" if (solicitante or "").upper() == "SEDUC" else ("SIMPLES" if solicitante else "")
        values.extend([
            data_exec.strftime("%d/%m/%Y") if data_exec else "",
            data_ref.strftime("%d/%m/%Y") if data_ref else "",
            indicativo,
            solicitante,
            chamado,
            cobranca,
        ])
        _write_row(ws, row_idx, values)

    _autosize_columns(ws, len(headers), len(pairings))


def _sheet_assistente(
    wb: Workbook,
    class_reports: List[ClassReport],
    class_to_idr: Dict[UUID, Optional[UUID]],
    turmas_map: Dict,
    discs_map: Dict,
    profs_map: Dict,
    dir_map: Dict,
    is_coord: bool = False,
) -> None:
    ws = wb.create_sheet("Assistente")
    headers = [
        "ID",
        "DATA",
        "DIA ",
        "TURNO",
        "ESTÚDIO",
        "CANAL",
        "CURSO",
        "HORÁRIO",
        "DISCIPLINA",
        "PROFESSOR",
        "REGULAR",
        "SUBSTITUIÇÃO DE PROFESSOR",
        "PROFESSOR QUE SUBSTITUIU",
        "INTERAÇÃO PROFESSOR ALUNO",
        "TIPO DE INTERAÇÃO",
        "ATIVIDADE PRÁTICA PARA ESCOLA",
        "TIPO DE ATIVIDADE PRÁTICA",
        "ATRASO PARA INÍCIO",
        "TEMPO DE ATRASO",
        "OBSERVAÇÃO ATRASO",
        "PROBLEMA COM MATERIAL ",
        "MOTIVO DO PROBLEMA",
        "UTILIZOU ALGUM RECURSO",
        "TIPO DE RECURSO",
        "FICHEIRO GERADO",
        "LINK DO VÍDEO",
        "LINK DO VIMEO",
        "LINK DO SLIDE (PDF)",
        "PASTA DO DRIVE",
    ]
    if not is_coord:
        headers.append("DIRETOR IMAGEM")
    headers.extend([
        "YOUTUBE LINK",
        "ESCOLAS PARTICIPANTES",
        "OBSERVAÇÕES (MANHÃ)",
        "TICKET NUMBER",
        "STATUS DE VALIDAÇÃO",
        "OBSERVAÇÃO DA COORDENAÇÃO",
        "VALIDADO POR",
        "TIPO DE AULA",
        "CONTEÚDO MINISTRADO",
        "BNCC / HABILIDADES",
        "STATUS COMPLIANCE",
        "OBSERVAÇÕES GERAIS",
        "MATERIAIS COM PROBLEMA",
    ])
    if not is_coord:
        headers.append("ID_RELATORIO_IMAGEM")
    headers.extend([
        "DATA DE EXECUÇÃO REAL",
        "DATA DE REFERÊNCIA",
        "INDICATIVO DE REPOSIÇÃO",
        "SOLICITANTE ANTECIPAÇÃO",
        "TIPO COBRANÇA SEDUC",
    ])
    _write_header(ws, headers)

    for row_idx, r in enumerate(class_reports, 2):
        turma = turmas_map.get(r.turma_id)
        disc = discs_map.get(r.disciplina_id)
        prof = profs_map.get(r.professor_id) if r.professor_id else None
        prof_sub = (
            profs_map.get(r.professor_substituto_id)
            if r.teve_substituicao and r.professor_substituto_id
            else None
        )
        diretor = dir_map.get(r.diretor_imagem_id) if r.diretor_imagem_id else None

        tem_interacao = r.interacao_professor_aluno and r.interacao_professor_aluno != "Não"
        tem_atividade = bool(r.atividade_pratica and r.atividade_pratica.strip())
        tem_problema = r.problema_material and r.problema_material != "Não"
        tem_recurso = _has_recursos_utilizados(r.tipo_recursos_utilizados)

        try:
            folder_link = r.video_folder_link or ""
        except Exception:
            folder_link = ""

        escolas_str = _safe_join_values(r.escolas_participantes)
        idr_link = class_to_idr.get(r.id)
        values = [
            str(r.id),
            r.data_aula.strftime("%d/%m/%Y") if r.data_aula else "",
            DIAS_PT.get(r.data_aula.weekday(), "") if r.data_aula else "",
            r.turno or "",
            r.estudio or "",
            r.canal_utilizado or "",
            turma.nome if turma else "",
            _class_horario_str(r, turma),
            disc.nome if disc else "",
            prof.nome if prof else (r.professor_nome_externo or ""),
            r.regular or "Sim",
            "Sim" if r.teve_substituicao else "Não",
            prof_sub.nome if prof_sub else "-",
            "Sim" if tem_interacao else "Não",
            r.interacao_professor_aluno if tem_interacao else "",
            "Sim" if tem_atividade else "Não",
            r.atividade_pratica or "",
            "sim" if r.teve_atraso else "não",
            str(r.minutos_atraso) if r.teve_atraso and r.minutos_atraso else "não",
            r.observacao_atraso or "",
            "Sim" if tem_problema else "Não",
            r.problema_material if tem_problema else "Não",
            "Sim" if tem_recurso else "Não",
            _safe_join_values(r.tipo_recursos_utilizados) if tem_recurso else "",
            r.nome_ficheiro_gerado or "",
            r.video_link or "",
            r.vimeo_link or "",
            r.slide_link or "",
            folder_link,
        ]
        if not is_coord:
            values.append(diretor.nome if diretor else "")
        values.extend([
            r.youtube_link or "",
            escolas_str,
            r.observacoes_manha or "",
            r.ticket_number or "",
            _status_label(r.status, r.precisa_correcao),
            r.observacao_coordenacao or "",
            r.validado_por_nome or "",
            r.tipo_aula or "",
            r.conteudo_ministrado or "",
            r.bncc_habilidades or "",
            r.status_compliance or "",
            r.observacoes or "",
            format_problematic_materials(r.problematic_materials),
        ])
        if not is_coord:
            values.append(str(idr_link) if idr_link else "")
        exec_val = getattr(r, "data_execucao_real", None)
        ref_val = getattr(r, "data_referencia_aula", None)
        values.extend([
            exec_val.strftime("%d/%m/%Y") if exec_val else "",
            ref_val.strftime("%d/%m/%Y") if ref_val else "",
            getattr(r, "motivo_referencia", "") or "",
            getattr(r, "solicitante_antecipacao", "") or "",
            # v4: tipo_cobranca_seduc não existe no banco; deduzido do pedido SEDUC
            ("DUPLA" if (getattr(r, "solicitante_antecipacao", "") or "").upper() == "SEDUC"
             else ("SIMPLES" if getattr(r, "solicitante_antecipacao", None) else "")),
        ])
        _write_row(ws, row_idx, values)

    _autosize_columns(ws, len(headers), len(class_reports))


def _checklist_columns(db: Session) -> List[Tuple[str, UUID]]:
    items = (
        db.query(ImageDirectorChecklistItem)
        .filter(ImageDirectorChecklistItem.ativo == True)  # noqa: E712
        .order_by(ImageDirectorChecklistItem.ordem, ImageDirectorChecklistItem.nome)
        .all()
    )
    return [(_safe_col_name("CHK", item.nome), item.id) for item in items]


def _question_columns(db: Session) -> List[Tuple[str, ImageDirectorCustomQuestion]]:
    items = (
        db.query(ImageDirectorCustomQuestion)
        .filter(ImageDirectorCustomQuestion.ativa == True)  # noqa: E712
        .order_by(ImageDirectorCustomQuestion.ordem, ImageDirectorCustomQuestion.texto)
        .all()
    )
    cols = []
    for q in items:
        prefix = "P" if q.nivel == "por_relatorio" else "A"
        cols.append((_safe_col_name(prefix, q.texto), q))
    return cols


def _answer_for_question(report: ImageDirectorReport, lesson, question: ImageDirectorCustomQuestion) -> str:
    if question.nivel == "por_relatorio":
        for ans in report.respostas_extras or []:
            if ans.lesson_id is None and ans.question_id == question.id:
                if question.tipo == "texto":
                    return ans.resposta_texto or ""
                return _fmt_bool(ans.resposta_bool)
        return ""
    if not lesson:
        return ""
    for ans in lesson.respostas_extras or []:
        if ans.question_id == question.id:
            if question.tipo == "texto":
                return ans.resposta_texto or ""
            return _fmt_bool(ans.resposta_bool)
    return ""


def _sheet_diretor_imagem(
    wb: Workbook,
    idr_reports: List[ImageDirectorReport],
    db: Session,
) -> None:
    ws = wb.create_sheet("Diretor Imagem")
    checklist_cols = _checklist_columns(db)
    question_cols = _question_columns(db)

    fixed_headers = [
        "ID_RELATORIO",
        "DATA",
        "TURNO",
        "ESTÚDIO",
        "CURSO",
        "DISCIPLINA",
        "PROFESSOR",
        "HORÁRIO",
        "REGULAR",
        "TICKET",
        "ORIGEM",
        "DIRETOR_IMAGEM",
        "CRIADO_POR",
        "HORÁRIO_ENTRADA",
        "HORÁRIO_SAÍDA",
        "YOUTUBE",
        "OBSERVAÇÕES_GERAIS",
        "STATUS",
        "CORREÇÃO_PENDENTE",
        "OBSERVAÇÃO_COORDENAÇÃO",
        "VALIDADO_POR",
        "VALIDADO_EM",
        "ID_RELATORIO_ASSISTENTE",
        "NUMERO_AULA",
        "TRANSMISSÃO_OU_GRAVADA",
        "CANAL",
        "Nº_CHAMADO",
        "VÍDEO_CORROMPIDO",
        "OBS_VÍDEO",
        "INTERRUPÇÕES",
        "PROBLEMA_ÁUDIO",
        "OBS_ÁUDIO",
        "VINHETAS_CORRETAS",
        "OBS_VINHETAS",
        "CRÉDITOS_CORRETOS",
        "OBS_AULA",
    ]
    dynamic_headers = [c[0] for c in checklist_cols] + [c[0] for c in question_cols]
    headers = fixed_headers + dynamic_headers
    _write_header(ws, headers)

    row_idx = 2
    for report in idr_reports:
        lessons = report.lessons or [None]
        for lesson in lessons:
            checklist_map = {resp.item_id: resp.resposta for resp in report.checklist_respostas or []}
            fixed = [
                str(report.id),
                report.data_relatorio.strftime("%d/%m/%Y") if report.data_relatorio else "",
                report.turno or "",
                report.estudio or "",
                report.turma_nome or "",
                report.disciplina_nome or "",
                report.professor_nome or "",
                _idr_horario_str(report),
                report.regular or "Sim",
                report.ticket_number or "",
                report.origem or "",
                report.diretor_imagem_nome or "",
                report.creator_name or "",
                _fmt_time(report.horario_entrada),
                _fmt_time(report.horario_saida),
                report.youtube_link or "",
                report.observacoes_gerais or "",
                _status_label(report.status, report.precisa_correcao),
                "Sim" if report.precisa_correcao else "Não",
                report.observacao_coordenacao or "",
                report.validado_por_nome or "",
                _fmt_datetime(report.validado_em),
                str(report.class_report_id) if report.class_report_id else "",
                lesson.numero_aula if lesson else "",
                lesson.transmissao_ou_gravada if lesson else "",
                lesson.canal_utilizado if lesson else "",
                lesson.numero_chamado if lesson else "",
                lesson.video_corrompido if lesson else "",
                lesson.video_corrompido_obs if lesson else "",
                lesson.interrupcoes if lesson else "",
                lesson.problema_audio if lesson else "",
                lesson.problema_audio_obs if lesson else "",
                lesson.vinhetas_corretas if lesson else "",
                lesson.vinhetas_corretas_obs if lesson else "",
                lesson.creditos_corretos if lesson else "",
                lesson.observacoes if lesson else "",
            ]
            dynamic = [_fmt_bool(checklist_map.get(item_id)) for _, item_id in checklist_cols]
            dynamic += [_answer_for_question(report, lesson, q) for _, q in question_cols]
            _write_row(ws, row_idx, fixed + dynamic)
            row_idx += 1

    _autosize_columns(ws, len(headers), max(row_idx - 2, 0))


def _package_as_xlsm(raw_xlsx_bytes: bytes) -> bytes:
    """Converte o pacote OpenXML para o MIME e tipo oficial de macro-enabled (.xlsm)."""
    import zipfile

    zin = zipfile.ZipFile(io.BytesIO(raw_xlsx_bytes), "r")
    buf = io.BytesIO()
    zout = zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED)
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == "[Content_Types].xml":
            data = data.replace(
                b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
                b"application/vnd.ms-excel.sheet.macroEnabled.main+xml",
            )
        zout.writestr(item, data)
    zout.close()
    zin.close()
    return buf.getvalue()


def build_audit_workbook(
    db: Session,
    filters: AuditExportFilters,
    user_role: Optional[str] = None,
    is_xlsm: bool = False,
    include_faturamento: bool = False,
) -> bytes:
    is_coord = user_role in ("coordenador", "coordenadora")
    class_reports = _load_class_reports(db, filters)
    idr_reports = [] if is_coord else _load_idr_reports(db, filters)
    turmas_map, discs_map, profs_map, dir_map = _load_lookup_maps(db, class_reports, idr_reports)
    pairings, class_to_idr = _build_pairings(class_reports, idr_reports)

    wb = Workbook()
    if is_xlsm or include_faturamento:
        ws_fat = wb.active
        ws_fat.title = "Faturamento SEDUC"
        _sheet_faturamento_seduc(ws_fat, pairings, turmas_map, discs_map, profs_map, dir_map, is_coord=is_coord)
        ws_cons = wb.create_sheet("Consolidado")
    else:
        ws_cons = wb.active
        ws_cons.title = "Consolidado"

    _sheet_consolidado(ws_cons, pairings, turmas_map, discs_map, profs_map, dir_map, is_coord=is_coord)
    _sheet_assistente(wb, class_reports, class_to_idr, turmas_map, discs_map, profs_map, dir_map, is_coord=is_coord)

    if not is_coord:
        _sheet_diretor_imagem(wb, idr_reports, db)

    output = io.BytesIO()
    wb.save(output)
    raw_bytes = output.getvalue()

    if is_xlsm:
        return _package_as_xlsm(raw_bytes)
    return raw_bytes
