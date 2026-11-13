"""Tests for consolidated turno PDF context (multiple slot reports)."""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.services.image_director_pdf import _aulas_from_reports, build_turno_context


def _report(horario, disciplina, numero_aula, turno="Manhã", estudio="ESTÚDIO 1"):
    lesson = SimpleNamespace(
        numero_aula=numero_aula,
        disciplina_nome=disciplina,
        professor_nome="Prof",
        transmissao_ou_gravada="Transmissão",
        numero_chamado=None,
        canal_utilizado="1",
        video_corrompido="Não",
        interrupcoes="Não",
        problema_audio="Não",
        vinhetas_corretas="Sim",
        creditos_corretos="Sim",
        video_corrompido_obs=None,
        problema_audio_obs=None,
        vinhetas_corretas_obs=None,
        observacoes=None,
        respostas_extras=[],
    )
    return SimpleNamespace(
        id=uuid4(),
        data_relatorio=date(2026, 9, 7),
        turno=turno,
        estudio=estudio,
        turma_nome="EM 1",
        diretor_imagem_nome="Diretor",
        disciplina_nome=disciplina,
        professor_nome="Prof",
        horario_aula=horario,
        regular="Sim",
        youtube_link="https://youtube.com/watch?v=abc",
        lessons=[lesson],
        checklist_respostas=[],
        respostas_extras=[],
        observacoes_gerais=None,
    )


def test_aulas_from_reports_accumulates_all_slots():
    reports = [
        _report("09:50 às 10:50", "MATEMÁTICA", 2),
        _report("08:30 às 09:30", "PORTUGUÊS", 1),
        _report("11:10 às 12:10", "HISTÓRIA", 3),
    ]
    aulas = _aulas_from_reports(reports)
    assert len(aulas) == 3
    assert [a["numero"] for a in aulas] == [1, 2, 3]
    assert [a["disciplina_nome"] for a in aulas] == ["PORTUGUÊS", "MATEMÁTICA", "HISTÓRIA"]


def test_build_turno_context_includes_all_lessons():
    reports = [
        _report("08:30 às 09:30", "PORTUGUÊS", 1),
        _report("09:50 às 10:50", "MATEMÁTICA", 2),
    ]
    ctx = build_turno_context(reports)
    assert len(ctx["aulas"]) == 2
    assert ctx["header"]["turno"] == "Manhã"


def test_build_turno_context_ti_dia_completo():
    reports = [
        _report("08:30 às 09:30", "PORTUGUÊS", 1, turno="Manhã"),
        _report("13:00 às 14:00", "MATEMÁTICA", 5, turno="Tarde"),
    ]
    ctx = build_turno_context(reports, dia_completo=True)
    assert len(ctx["aulas"]) == 2
    assert ctx["header"]["turno"] == "Integral — Dia completo"
    assert [a["numero"] for a in ctx["aulas"]] == [1, 5]


def test_aulas_from_reports_tecnico_turno_only():
    """Simula PDF por turno: apenas relatórios do mesmo turno entram no lote."""
    reports_manha = [
        _report("08:30 às 09:30", "PORTUGUÊS", 1, turno="Manhã"),
        _report("09:50 às 10:50", "MATEMÁTICA", 2, turno="Manhã"),
    ]
    aulas = _aulas_from_reports(reports_manha)
    assert len(aulas) == 2
    assert all(r.turno == "Manhã" for r in reports_manha)

    reports_tarde = [_report("13:00 às 14:00", "HISTÓRIA", 1, turno="Tarde")]
    aulas_tarde = _aulas_from_reports(reports_tarde)
    assert len(aulas_tarde) == 1
    assert aulas_tarde[0]["numero"] == 1
