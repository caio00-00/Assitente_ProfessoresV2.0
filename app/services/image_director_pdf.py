"""
Canal Educação v3.2 — Geração do PDF do Relatório do Diretor de Imagem.

Usa xhtml2pdf (pure-Python, não exige libs de sistema como pango/cairo,
diferente do WeasyPrint) para renderizar o mesmo template Jinja2 usado na
pré-visualização em tela, no formato do relatório manual em papel.
"""

import io
import os

from fastapi.templating import Jinja2Templates
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from xhtml2pdf import pisa

from app.models.image_director_report import ImageDirectorReport
from app.services.horario_resolver import format_faixa, ordinal_horario

LETTERHEAD_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "static",
    "pdf",
    "oros_letterhead.png",
)


def _templates() -> Jinja2Templates:
    templates_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "templates"
    )
    return Jinja2Templates(directory=templates_dir)


def _letterhead_page_pdf() -> bytes | None:
    """Uma página A4 só com o timbrado Oros (fundo)."""
    if not os.path.isfile(LETTERHEAD_PATH):
        return None
    buf = io.BytesIO()
    page_w, page_h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawImage(ImageReader(LETTERHEAD_PATH), 0, 0, width=page_w, height=page_h, mask="auto")
    c.showPage()
    c.save()
    return buf.getvalue()


def _apply_letterhead(pdf_bytes: bytes) -> bytes:
    """Sobrepõe o timbrado atrás de cada página (xhtml2pdf não suporta fundo fixo)."""
    letterhead_pdf = _letterhead_page_pdf()
    if not letterhead_pdf:
        return pdf_bytes

    content_reader = PdfReader(io.BytesIO(pdf_bytes))
    if not content_reader.pages:
        return pdf_bytes

    writer = PdfWriter()
    for page in content_reader.pages:
        lh_reader = PdfReader(io.BytesIO(letterhead_pdf))
        # v4: a página do timbrado entra no writer ANTES do merge. O pypdf 7
        # removeu o merge em páginas soltas (era o que quebrava o PDF do turno).
        bg = writer.add_page(lh_reader.pages[0])
        bg.merge_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def build_report_context(report: ImageDirectorReport) -> dict:
    """Monta o contexto usado tanto na pré-visualização HTML quanto no PDF."""

    checklist = []
    for resp in report.checklist_respostas:
        checklist.append(
            {
                "nome": resp.item.nome if resp.item else "—",
                "resposta": "Sim" if resp.resposta else ("Não" if resp.resposta is False else "—"),
            }
        )

    perguntas_relatorio = []
    for ans in report.respostas_extras:
        if ans.lesson_id is not None:
            continue
        perguntas_relatorio.append(
            {
                "texto": ans.question.texto if ans.question else "—",
                "resposta": ans.resposta_texto
                if ans.question and ans.question.tipo == "texto"
                else ("Sim" if ans.resposta_bool else "Não"),
            }
        )

    lessons = []
    for lesson in report.lessons:
        perguntas_aula = []
        for ans in lesson.respostas_extras:
            perguntas_aula.append(
                {
                    "texto": ans.question.texto if ans.question else "—",
                    "resposta": ans.resposta_texto
                    if ans.question and ans.question.tipo == "texto"
                    else ("Sim" if ans.resposta_bool else "Não"),
                }
            )
        lessons.append({"lesson": lesson, "perguntas_extras": perguntas_aula})

    return {
        "report": report,
        "horario_exato": horario_exato_label(report),
        "lessons": lessons,
        "checklist": checklist,
        "perguntas_relatorio": perguntas_relatorio,
    }


def render_report_html(report: ImageDirectorReport, request) -> str:
    templates = _templates()
    context = build_report_context(report)
    context["request"] = request
    template = templates.get_template("image_director_report_pdf.html")
    return template.render(context)


def render_report_pdf(report: ImageDirectorReport, request) -> bytes:
    """Renderiza o relatório para PDF e retorna os bytes do arquivo."""
    html = render_report_html(report, request)
    output = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=output, encoding="utf-8")
    if result.err:
        raise RuntimeError("Falha ao gerar o PDF do relatório de imagem.")
    return _apply_letterhead(output.getvalue())


def _obs_rows_from_lesson(lesson) -> list:
    rows = []
    if not lesson:
        return rows
    if lesson.video_corrompido_obs:
        rows.append({"q": "Descrição do vídeo corrompido", "a": lesson.video_corrompido_obs})
    if lesson.problema_audio_obs:
        rows.append({"q": "Descrição do problema de áudio", "a": lesson.problema_audio_obs})
    if lesson.vinhetas_corretas_obs:
        rows.append({"q": "Descrição do problema com as vinhetas", "a": lesson.vinhetas_corretas_obs})
    return rows


def horario_exato_label(report) -> str:
    """
    Horário do slot para exibição: 'HH:MM às HH:MM (3º Horário)'.
    Usa `_slot_times` (resolvido pela grade/turno/modalidade na rota) ou
    start_time/end_time persistidos; sem horários, cai no texto original.
    """
    horario = (getattr(report, "horario_aula", None) or "").strip()
    times = getattr(report, "_slot_times", None) or (
        getattr(report, "start_time", None),
        getattr(report, "end_time", None),
    )
    faixa = format_faixa(times[0], times[1]) if times else None
    if not faixa:
        return horario
    ordinal = getattr(report, "_slot_ordinal", None) or ordinal_horario(horario)
    if ordinal:
        return f"{faixa} ({ordinal}º Horário)"
    return faixa


def _lesson_row_from_lesson(report: ImageDirectorReport, lesson, fallback_numero: int) -> dict:
    """Monta bloco de aula a partir de uma lição do relatório."""
    numero_aula = lesson.numero_aula if lesson and lesson.numero_aula else fallback_numero
    detalhes = []
    perguntas_extras = []
    if lesson:
        detalhes = [
            {"q": "Foi transmissão ou aula gravada?", "a": lesson.transmissao_ou_gravada},
        ]
        if lesson.transmissao_ou_gravada == "Aula gravada" and lesson.numero_chamado:
            detalhes.append({"q": "Nº chamado", "a": lesson.numero_chamado})
        detalhes.extend([
            {"q": "Vídeo corrompido?", "a": lesson.video_corrompido},
            {"q": "Interrupções?", "a": lesson.interrupcoes},
            {"q": "Problema de áudio?", "a": lesson.problema_audio},
            {"q": "Vinhetas corretas?", "a": lesson.vinhetas_corretas},
            {"q": "Créditos corretos?", "a": lesson.creditos_corretos},
        ])
        for ans in lesson.respostas_extras:
            perguntas_extras.append(
                {
                    "texto": ans.question.texto if ans.question else "—",
                    "resposta": ans.resposta_texto
                    if ans.question and ans.question.tipo == "texto"
                    else ("Sim" if ans.resposta_bool else "Não"),
                }
            )
    return {
        "numero": numero_aula,
        "disciplina_nome": (lesson.disciplina_nome if lesson else None)
        or report.disciplina_nome
        or "—",
        "professor_nome": (lesson.professor_nome if lesson else None) or report.professor_nome,
        "horario": horario_exato_label(report),
        "regular": getattr(report, "regular", "Sim") or "Sim",
        "canal": lesson.canal_utilizado if lesson else "",
        "youtube": report.youtube_link or "",
        "detalhes": detalhes,
        "obs_rows": _obs_rows_from_lesson(lesson),
        "perguntas_extras": perguntas_extras,
        "observacoes": lesson.observacoes if lesson else None,
    }


def _lesson_row_from_report(report: ImageDirectorReport, numero: int) -> dict:
    """Monta bloco de aula a partir de um ImageDirectorReport (v3.3)."""
    lesson = report.lessons[0] if report.lessons else None
    return _lesson_row_from_lesson(report, lesson, numero)


def _aulas_from_reports(reports: list) -> list:
    """Consolida todas as aulas de N relatórios (1 slot = 1 report) em ordem."""
    sorted_reports = sorted(
        reports,
        key=lambda r: (
            min((l.numero_aula for l in r.lessons if l.numero_aula), default=999),
            r.horario_aula or "",
        ),
    )
    aulas = []
    for report in sorted_reports:
        if report.lessons:
            for lesson in sorted(report.lessons, key=lambda l: l.numero_aula or 0):
                aulas.append(_lesson_row_from_lesson(report, lesson, len(aulas) + 1))
        else:
            aulas.append(_lesson_row_from_report(report, len(aulas) + 1))
    aulas.sort(key=lambda a: (a["numero"], a.get("horario") or ""))
    return aulas


def build_turno_context(reports: list, *, dia_completo: bool = False) -> dict:
    """Contexto para PDF consolidado de um turno (vários relatórios origem=grade)."""
    if not reports:
        return {}
    header_report = reports[0]
    turno_label = header_report.turno
    if dia_completo:
        turnos = sorted({r.turno for r in reports if r.turno})
        if len(turnos) > 1:
            turno_label = "Integral — Dia completo"
        elif turnos:
            turno_label = turnos[0]

    checklist = []
    checklist_source = next(
        (r for r in reversed(reports) if r.checklist_respostas),
        header_report,
    )
    for resp in checklist_source.checklist_respostas:
        checklist.append(
            {
                "nome": resp.item.nome if resp.item else "—",
                "resposta": "Sim" if resp.resposta else ("Não" if resp.resposta is False else "—"),
            }
        )

    perguntas_relatorio = []
    for ans in header_report.respostas_extras:
        if ans.lesson_id is not None:
            continue
        perguntas_relatorio.append(
            {
                "texto": ans.question.texto if ans.question else "—",
                "resposta": ans.resposta_texto
                if ans.question and ans.question.tipo == "texto"
                else ("Sim" if ans.resposta_bool else "Não"),
            }
        )

    aulas = _aulas_from_reports(reports)

    return {
        "header": {
            "turma_nome": header_report.turma_nome,
            "turno": turno_label,
            "data_fmt": header_report.data_relatorio.strftime("%d/%m/%Y"),
            "estudio": header_report.estudio,
            "diretor_nome": header_report.diretor_imagem_nome,
        },
        "aulas": aulas,
        "checklist": checklist,
        "observacoes_gerais": checklist_source.observacoes_gerais,
        "perguntas_relatorio": perguntas_relatorio,
    }


def render_turno_pdf(reports: list, request, *, dia_completo: bool = False) -> bytes:
    """Renderiza PDF consolidado do turno."""
    templates = _templates()
    context = build_turno_context(reports, dia_completo=dia_completo)
    context["request"] = request
    template = templates.get_template("image_director_turno_pdf.html")
    html = template.render(context)
    output = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=output, encoding="utf-8")
    if result.err:
        raise RuntimeError("Falha ao gerar o PDF consolidado do turno.")
    return _apply_letterhead(output.getvalue())
