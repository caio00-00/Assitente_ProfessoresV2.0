"""
Testes automatizados da Etapa 6:
- Item 1: Emissão e estruturação de relatórios em formato .xlsm (macro-enabled) com aba oficial de Faturamento SEDUC.
- Item 2: Remoção/ocultação de Diretor de Imagem quando o usuário logado for Coordenador (tanto em auditoria quanto em agenda).
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, time
from typing import Dict

import pytest
from openpyxl import load_workbook

from app.models.auxiliares import Disciplina, Professor
from app.models.class_report import ClassReport
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import ImageDirectorReport
from app.models.user import User
from app.services.agenda_export import exportar_periodo
from app.services.audit_export import AuditExportFilters, build_audit_workbook


@pytest.fixture
def coordenador_user(db_session) -> User:
    coord = User(
        email="coord.etapa6@escola.gov.br",
        full_name="Coordenadora Pedagógica",
        role="coordenador",
        is_active=True,
    )
    coord.set_password("coord123")
    db_session.add(coord)
    db_session.commit()
    db_session.refresh(coord)
    return coord


@pytest.fixture
def seed_faturamento(db_session, admin_user, sample_turma, sample_professor_disciplina) -> Dict:
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]

    diretor = DiretorImagem(nome="Roberto Diretor de Imagem", user_id=admin_user.id, is_active=True)
    db_session.add(diretor)
    db_session.flush()

    # Relatório de Aula com dados completos de Faturamento SEDUC (Etapa 5)
    cr = ClassReport(
        created_by=admin_user.id,
        data_aula=date(2026, 10, 15),
        data_execucao_real=date(2026, 10, 15),
        data_referencia_aula=date(2026, 9, 28),
        motivo_referencia="Gravação por reposição/falta, referente à aula do dia 28/09/2026",
        solicitante_antecipacao="SEDUC",
        ticket_number="SEDUC-CHAMADO-998877",
        turno="Manhã",
        estudio="Estúdio 01",
        turma_id=sample_turma.id,
        disciplina_id=disc.id,
        professor_id=prof.id,
        diretor_imagem_id=diretor.id,
        horario_aula="07:30 - 08:30",
        start_time=time(7, 30),
        end_time=time(8, 30),
        regular="Sim",
        tipo_aula="Gravação de aula",
        canal_utilizado="1",
        conteudo_ministrado="Aprofundamento Álgebra",
        status="VALIDADO",
    )
    db_session.add(cr)
    db_session.flush()

    idr = ImageDirectorReport(
        created_by=admin_user.id,
        diretor_imagem_id=diretor.id,
        data_relatorio=date(2026, 10, 15),
        turno="Manhã",
        estudio="Estúdio 01",
        turma_id=sample_turma.id,
        disciplina_id=disc.id,
        professor_id=prof.id,
        horario_aula="07:30 - 08:30",
        class_report_id=cr.id,
        origem="gravacao_estudio",
        status="VALIDADO",
        ticket_number="SEDUC-CHAMADO-998877",
        solicitante_antecipacao="SEDUC",
        data_referencia=date(2026, 9, 28),
        motivo_referencia="Gravação por reposição/falta, referente à aula do dia 28/09/2026",
    )
    db_session.add(idr)
    db_session.commit()
    return {"cr": cr, "idr": idr, "diretor": diretor}


class TestEtapa6CoordenadorPermissoes:
    def test_build_audit_workbook_coordenador_oculta_diretor_imagem(self, db_session, seed_faturamento):
        """Coordenador não deve ver a aba 'Diretor Imagem' nem colunas de Diretor de Imagem."""
        xlsx_bytes = build_audit_workbook(
            db_session,
            AuditExportFilters(),
            user_role="coordenador",
            is_xlsm=False,
            include_faturamento=False,
        )
        wb = load_workbook(io.BytesIO(xlsx_bytes))

        # 1. Aba Diretor Imagem não pode existir para coordenador
        assert "Diretor Imagem" not in wb.sheetnames
        assert wb.sheetnames == ["Consolidado", "Assistente"]

        # 2. Na aba Consolidado, a coluna DIRETOR_IMAGEM não pode estar nos cabeçalhos
        ws_cons = wb["Consolidado"]
        headers_cons = [cell.value for cell in ws_cons[1]]
        assert "DIRETOR_IMAGEM" not in headers_cons
        assert "STATUS_IMAGEM" not in headers_cons
        assert "YOUTUBE_IMAGEM" not in headers_cons

        # 3. Na aba Assistente, a coluna DIRETOR IMAGEM não pode estar nos cabeçalhos
        ws_assist = wb["Assistente"]
        headers_assist = [cell.value for cell in ws_assist[1]]
        assert "DIRETOR IMAGEM" not in headers_assist

    def test_build_audit_workbook_admin_visualiza_diretor_imagem(self, db_session, seed_faturamento):
        """Admin deve continuar visualizando normalmente todas as 3 abas e a coluna de Diretor de Imagem."""
        xlsx_bytes = build_audit_workbook(
            db_session,
            AuditExportFilters(),
            user_role="admin",
            is_xlsm=False,
            include_faturamento=False,
        )
        wb = load_workbook(io.BytesIO(xlsx_bytes))
        assert "Diretor Imagem" in wb.sheetnames
        assert wb.sheetnames == ["Consolidado", "Assistente", "Diretor Imagem"]

        ws_cons = wb["Consolidado"]
        headers_cons = [cell.value for cell in ws_cons[1]]
        assert "DIRETOR_IMAGEM" in headers_cons

        ws_assist = wb["Assistente"]
        headers_assist = [cell.value for cell in ws_assist[1]]
        assert "DIRETOR IMAGEM" in headers_assist

    def test_agenda_export_coordenador_oculta_linha_diretor(self, db_session, seed_faturamento):
        """Na exportação da Agenda de Estúdios, o coordenador não deve ter a linha de Diretor."""
        hoje = date(2026, 10, 15)
        # Exportação para coordenador
        buf_coord = exportar_periodo(db_session, hoje, hoje, user_role="coordenador")
        wb_coord = load_workbook(buf_coord)
        ws_coord = wb_coord.active

        valores_coluna_a = [ws_coord.cell(row=r, column=1).value for r in range(1, 30)]
        assert "Diretor" not in valores_coluna_a

        # Exportação para admin
        buf_admin = exportar_periodo(db_session, hoje, hoje, user_role="admin")
        wb_admin = load_workbook(buf_admin)
        ws_admin = wb_admin.active
        valores_coluna_a_admin = [ws_admin.cell(row=r, column=1).value for r in range(1, 30)]
        assert "Diretor" in valores_coluna_a_admin


class TestEtapa6ExportacaoXLSM:
    def test_build_audit_workbook_xlsm_estrutura_e_macro_enabled(self, db_session, seed_faturamento):
        """Exportação .xlsm deve gerar pacote macroEnabled com aba Faturamento SEDUC no início."""
        xlsm_bytes = build_audit_workbook(
            db_session,
            AuditExportFilters(),
            user_role="admin",
            is_xlsm=True,
            include_faturamento=True,
        )

        # 1. Validação do manifesto OpenXML para macroEnabled
        zf = zipfile.ZipFile(io.BytesIO(xlsm_bytes))
        content_types = zf.read("[Content_Types].xml").decode("utf-8")
        assert "application/vnd.ms-excel.sheet.macroEnabled.main+xml" in content_types

        # 2. Validação das abas (Faturamento SEDUC como primeira aba)
        wb = load_workbook(io.BytesIO(xlsm_bytes))
        assert wb.sheetnames[0] == "Faturamento SEDUC"
        assert "Consolidado" in wb.sheetnames
        assert "Assistente" in wb.sheetnames
        assert "Diretor Imagem" in wb.sheetnames

        # 3. Validação das colunas oficiais de Faturamento SEDUC
        ws_fat = wb["Faturamento SEDUC"]
        headers_fat = [cell.value for cell in ws_fat[1]]
        expected_cols = [
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
            "DIRETOR_IMAGEM",
            "É_ANTECIPAÇÃO",
            "SOLICITANTE_ANTECIPAÇÃO",
            "Nº_CHAMADO_SEDUC",
            "COBRANÇA_SEDUC",
            "VALOR_FATURÁVEL",
            "STATUS_ASSISTENTE",
            "STATUS_DIR_IMAGEM",
            "CONGRUÊNCIA_MODALIDADE",
        ]
        for col in expected_cols:
            assert col in headers_fat, f"Coluna obrigatória ausente em Faturamento SEDUC: {col}"

        # 4. Validação dos dados preenchidos na linha de faturamento
        row2 = [cell.value for cell in ws_fat[2]]
        assert "15/10/2026" in row2
        assert "10/2026" in row2
        assert "28/09/2026" in row2
        assert "09/2026" in row2
        assert "Gravação por reposição/falta, referente à aula do dia 28/09/2026" in row2
        assert "SEDUC-CHAMADO-998877" in row2
        assert "DUPLA" in row2

    def test_api_export_endpoint_xlsm(self, client, admin_headers, seed_faturamento):
        """Endpoint /api/v1/reports/export com formato=xlsm deve responder com Content-Type correto e extensão .xlsm."""
        res = client.get("/api/v1/reports/export?formato=xlsm", headers=admin_headers)
        assert res.status_code == 200
        assert "application/vnd.ms-excel.sheet.macroEnabled.12" in res.headers["content-type"]
        assert ".xlsm" in res.headers["content-disposition"]

        # Verifica integridade do binário
        wb = load_workbook(io.BytesIO(res.content))
        assert wb.sheetnames[0] == "Faturamento SEDUC"
