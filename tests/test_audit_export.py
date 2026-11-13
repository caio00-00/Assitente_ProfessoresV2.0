"""
Tests for audit export workbook (3 abas: Consolidado, Assistente, Diretor Imagem).
"""

import io
import uuid
from datetime import date, time
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app.models.class_report import ClassReport
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import ImageDirectorReport
from app.services.audit_export import (
    AuditExportFilters,
    _build_pairings,
    _sanitize_excel_value,
    build_audit_workbook,
    format_problematic_materials,
)


class TestFormatProblematicMaterials:
    def test_empty(self):
        assert format_problematic_materials(None) == ""
        assert format_problematic_materials([]) == ""

    def test_strips_illegal_xml_chars(self):
        raw = "• item\x0bcom tab vertical"
        assert "\x0b" not in _sanitize_excel_value(raw)
        assert "• item" in _sanitize_excel_value(raw)

    def test_dict_items(self):
        materials = [
            {"material": "Projetor", "descricao": "Sem imagem"},
            {"nome": "Microfone", "description": "Ruído"},
        ]
        result = format_problematic_materials(materials)
        assert "[Projetor]: Sem imagem" in result
        assert "[Microfone]: Ruído" in result

    def test_plain_strings(self):
        assert format_problematic_materials(["Cabo HDMI"]) == "Cabo HDMI"


class TestSafeJoinValues:
    def test_int_recursos_no_crash(self, db_session, admin_user, sample_turma, sample_professor_disciplina):
        prof = sample_professor_disciplina["professor"]
        disc = sample_professor_disciplina["disciplina"]
        cr = ClassReport(
            created_by=admin_user.id,
            data_aula=date(2026, 3, 15),
            turno="Manhã",
            estudio="Estúdio 01",
            turma_id=sample_turma.id,
            disciplina_id=disc.id,
            professor_id=prof.id,
            horario_aula="07:30 - 08:30",
            regular="Sim",
            tipo_aula="Transmissão ao vivo",
            canal_utilizado="1",
            conteudo_ministrado="Funções",
            tipo_recursos_utilizados=123,
            status="VALIDADO",
        )
        db_session.add(cr)
        db_session.commit()
        xlsx = build_audit_workbook(db_session, AuditExportFilters())
        wb = load_workbook(io.BytesIO(xlsx))
        assert "Assistente" in wb.sheetnames

    def test_illegal_chars_in_text_fields(self, db_session, admin_user, sample_turma, sample_professor_disciplina):
        prof = sample_professor_disciplina["professor"]
        disc = sample_professor_disciplina["disciplina"]
        texto = (
            "• Como classificar relações entre espécies\x0b"
            "• Harmônicas: mutualismo\x0b"
            "• Desarmônicas: competição"
        )
        cr = ClassReport(
            created_by=admin_user.id,
            data_aula=date(2026, 3, 15),
            turno="Manhã",
            estudio="Estúdio 01",
            turma_id=sample_turma.id,
            disciplina_id=disc.id,
            professor_id=prof.id,
            horario_aula="07:30 - 08:30",
            regular="Sim",
            tipo_aula="Transmissão ao vivo",
            canal_utilizado="1",
            conteudo_ministrado="BIOLOGIA",
            observacoes=texto,
            bncc_habilidades=texto,
            status="VALIDADO",
        )
        db_session.add(cr)
        db_session.commit()
        xlsx = build_audit_workbook(db_session, AuditExportFilters())
        wb = load_workbook(io.BytesIO(xlsx))
        ws = wb["Assistente"]
        obs_col = [c.value for c in ws[1]].index("OBSERVAÇÕES GERAIS") + 1
        cell_val = ws.cell(row=2, column=obs_col).value or ""
        assert "\x0b" not in cell_val
        assert "mutualismo" in cell_val


class TestBuildPairings:
    def _make_cr(self, **kwargs):
        defaults = dict(
            id=uuid.uuid4(),
            data_aula=date(2026, 3, 15),
            turno="Manhã",
            estudio="Estúdio 01",
            turma_id=uuid.uuid4(),
            disciplina_id=uuid.uuid4(),
            horario_aula="07:30 - 08:30",
            youtube_link="https://youtube.com/watch?v=abc123",
            professor_nome="Prof Teste",
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def _make_idr(self, **kwargs):
        defaults = dict(
            id=uuid.uuid4(),
            data_relatorio=date(2026, 3, 15),
            turno="Manhã",
            estudio="Estúdio 01",
            turma_id=uuid.uuid4(),
            disciplina_id=uuid.uuid4(),
            horario_aula="07:30 - 08:30",
            class_report_id=None,
            youtube_link=None,
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_pairs_by_class_report_id(self):
        cr = self._make_cr()
        idr = self._make_idr(class_report_id=cr.id)
        rows, class_to_idr = _build_pairings([cr], [idr])
        assert len(rows) == 1
        assert rows[0] == (cr, idr)
        assert class_to_idr[cr.id] == idr.id

    def test_orphan_idr_appears_without_class(self):
        cr = self._make_cr()
        orphan = self._make_idr(
            data_relatorio=date(2026, 3, 16),
            estudio="Estúdio 02",
        )
        rows, _ = _build_pairings([cr], [orphan])
        assert len(rows) == 2
        paired = [r for r in rows if r[0] is cr][0]
        orphan_row = [r for r in rows if r[0] is None][0]
        assert paired[1] is None
        assert orphan_row[1] is orphan


@pytest.fixture
def audit_export_seed(db_session, admin_user, sample_turma, sample_professor_disciplina):
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    diretor = DiretorImagem(nome="Maria Diretora", user_id=admin_user.id, is_active=True)
    db_session.add(diretor)
    db_session.flush()

    cr = ClassReport(
        created_by=admin_user.id,
        data_aula=date(2026, 3, 15),
        turno="Manhã",
        estudio="Estúdio 01",
        turma_id=sample_turma.id,
        disciplina_id=disc.id,
        professor_id=prof.id,
        horario_aula="07:30 - 08:30",
        start_time=time(7, 30),
        end_time=time(8, 30),
        regular="Sim",
        tipo_aula="Transmissão ao vivo",
        canal_utilizado="1",
        conteudo_ministrado="Funções",
        youtube_link="https://youtube.com/watch?v=paired123",
        status="VALIDADO",
    )
    db_session.add(cr)
    db_session.flush()

    idr = ImageDirectorReport(
        created_by=admin_user.id,
        diretor_imagem_id=diretor.id,
        data_relatorio=date(2026, 3, 15),
        turno="Manhã",
        estudio="Estúdio 01",
        turma_id=sample_turma.id,
        disciplina_id=disc.id,
        professor_id=prof.id,
        horario_aula="07:30 - 08:30",
        class_report_id=cr.id,
        origem="grade",
        status="VALIDADO",
        youtube_link="https://youtube.com/watch?v=paired123",
    )
    orphan = ImageDirectorReport(
        created_by=admin_user.id,
        diretor_imagem_id=diretor.id,
        data_relatorio=date(2026, 3, 16),
        turno="Tarde",
        estudio="Estúdio 02",
        turma_id=sample_turma.id,
        disciplina_id=disc.id,
        professor_id=prof.id,
        horario_aula="14:00 - 15:00",
        origem="gravacao_estudio",
        status="RASCUNHO",
    )
    db_session.add_all([idr, orphan])
    db_session.commit()
    return {"class_report": cr, "idr": idr, "orphan_idr": orphan}


class TestBuildAuditWorkbook:
    def test_three_sheets(self, db_session, audit_export_seed):
        xlsx = build_audit_workbook(db_session, AuditExportFilters())
        wb = load_workbook(io.BytesIO(xlsx))
        assert wb.sheetnames == ["Consolidado", "Assistente", "Diretor Imagem"]

    def test_consolidado_vinculado(self, db_session, audit_export_seed):
        xlsx = build_audit_workbook(db_session, AuditExportFilters())
        wb = load_workbook(io.BytesIO(xlsx))
        ws = wb["Consolidado"]
        headers = [c.value for c in ws[1]]
        vinc_idx = headers.index("VINCULADO") + 1
        values = {row[vinc_idx - 1].value for row in ws.iter_rows(min_row=2)}
        assert "Sim" in values
        assert "Não" in values
