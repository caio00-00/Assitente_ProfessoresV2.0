"""Testes das correções do plano Relatórios v3 (fases 1–4)."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.rotas_diretor_imagem import (
    _fetch_grade_reports_for_pdf,
    create_report,
    list_reports,
)
from app.api.rotas_report import finalizar_relatorio
from app.core.security import get_password_hash
from app.models.auxiliares import Disciplina
from app.models.class_report import ClassReport
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import ImageDirectorReport, ImageDirectorLesson
from app.models.user import User
from app.schemas.image_director_report import ImageDirectorLessonCreate, ImageDirectorReportCreate
from app.utils.text_utils import is_placeholder_professor


def _chefe_user(db_session):
    user = User(
        email="chefe@test.com",
        full_name="Diretor Chefe Test",
        role="diretor_chefe",
        hashed_password=get_password_hash("test123"),
        email_confirmed=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _diretor_cadastro(db_session, nome: str, user=None):
    diretor = DiretorImagem(nome=nome, user_id=user.id if user else None, is_active=True)
    db_session.add(diretor)
    db_session.commit()
    db_session.refresh(diretor)
    return diretor


def _report_payload(diretor_id, turma_id, disc_id, **extra):
    base = {
        "diretor_imagem_id": diretor_id,
        "data_relatorio": date(2026, 9, 7),
        "turno": "Manhã",
        "estudio": "ESTÚDIO 1",
        "turma_id": turma_id,
        "disciplina_id": disc_id,
        "disciplina_nome": "MATEMÁTICA",
        "professor_nome_externo": "Prof. Silva",
        "horario_aula": "08:30 às 09:30",
        "origem": "grade",
    }
    base.update(extra)
    return ImageDirectorReportCreate(**base)


def _class_report(db_session, created_by, turma, disc, **extra):
    cr = ClassReport(
        created_by=created_by,
        data_aula=date(2026, 9, 7),
        turno="Manhã",
        estudio="Estúdio 01",
        turma_id=turma.id,
        disciplina_id=disc.id,
        professor_id=extra.pop("professor_id", None),
        professor_nome_externo=extra.pop("professor_nome_externo", None),
        horario_aula="08:30 às 09:30",
        regular="Sim",
        tipo_aula="Transmissão ao vivo",
        canal_utilizado="1",
        conteudo_ministrado="Conteudo teste",
        status=extra.pop("status", "AGUARDANDO_VALIDACAO"),
        youtube_link=extra.pop("youtube_link", "https://youtube.com/watch?v=abc"),
    )
    db_session.add(cr)
    db_session.commit()
    db_session.refresh(cr)
    return cr


def _idr_report(db_session, chefe, diretor, turma, disc, **extra):
    payload = _report_payload(
        diretor.id,
        turma.id,
        disc.id,
        class_report_id=extra.get("class_report_id"),
        turno=extra.get("turno", "Manhã"),
        horario_aula=extra.get("horario_aula", "08:30 às 09:30"),
    )
    report = create_report(payload, db_session, chefe)
    report.status = extra.get("status", "AGUARDANDO_VALIDACAO")
    db_session.add(
        ImageDirectorLesson(
            report_id=report.id,
            numero_aula=extra.get("numero_aula", 1),
            disciplina_nome="MATEMÁTICA",
            professor_nome="Prof. Silva",
            transmissao_ou_gravada="Transmissão",
            canal_utilizado="1",
            video_corrompido="Não",
            interrupcoes="Não",
            problema_audio="Não",
            vinhetas_corretas="Sim",
            creditos_corretos="Sim",
        )
    )
    db_session.commit()
    db_session.refresh(report)
    return report


class TestPlaceholderProfessor:
    def test_is_placeholder_professor(self):
        assert is_placeholder_professor("N/A") is True
        assert is_placeholder_professor("—") is True
        assert is_placeholder_professor("") is True
        assert is_placeholder_professor("Maria Souza") is False

    def test_lesson_create_rejects_na_professor(self):
        with pytest.raises(ValidationError):
            ImageDirectorLessonCreate(
                disciplina_nome="MATEMÁTICA",
                professor_nome="N/A",
                transmissao_ou_gravada="Transmissão",
                canal_utilizado="1",
            )

    def test_report_create_rejects_na_professor_externo(self, sample_turma, sample_professor_disciplina):
        disc = sample_professor_disciplina["disciplina"]
        with pytest.raises(ValidationError):
            ImageDirectorReportCreate(
                diretor_imagem_id=uuid4(),
                data_relatorio=date(2026, 9, 7),
                turno="Manhã",
                estudio="ESTÚDIO 1",
                turma_id=sample_turma.id,
                disciplina_id=disc.id,
                disciplina_nome="MATEMÁTICA",
                professor_nome_externo="N/A",
                horario_aula="08:30 às 09:30",
            )


class TestDiretorChefeCreateReport:
    def test_chefe_cria_em_nome_de_outro_diretor(self, db_session, sample_turma, sample_professor_disciplina):
        chefe = _chefe_user(db_session)
        diretor_alvo = _diretor_cadastro(db_session, "Carlos Diretor Imagem")
        _diretor_cadastro(db_session, "Outro Diretor")
        disc = sample_professor_disciplina["disciplina"]

        payload = _report_payload(
            diretor_alvo.id,
            sample_turma.id,
            disc.id,
            class_report_id=uuid4(),
        )
        report = create_report(payload, db_session, chefe)
        assert report.diretor_imagem_id == diretor_alvo.id
        assert report.created_by == chefe.id

    def test_chefe_diretor_inexistente_rejeitado(self, db_session, sample_turma, sample_professor_disciplina):
        chefe = _chefe_user(db_session)
        disc = sample_professor_disciplina["disciplina"]
        payload = ImageDirectorReportCreate(
            diretor_imagem_id=uuid4(),
            data_relatorio=date(2026, 9, 7),
            turno="Manhã",
            estudio="ESTÚDIO 1",
            turma_id=sample_turma.id,
            disciplina_id=disc.id,
            disciplina_nome="MATEMÁTICA",
            professor_nome_externo="Prof. Silva",
            horario_aula="08:30 às 09:30",
        )
        with pytest.raises(HTTPException) as exc:
            create_report(payload, db_session, chefe)
        assert exc.value.status_code == 404


class TestListReportsCreatedBy:
    def test_filtra_idr_pelo_created_by_do_class_report(
        self, db_session, sample_turma, sample_professor_disciplina, assistant_user, admin_user
    ):
        chefe = _chefe_user(db_session)
        diretor = _diretor_cadastro(db_session, "Diretor Filtro")
        disc = sample_professor_disciplina["disciplina"]

        cr_assistente = _class_report(db_session, assistant_user.id, sample_turma, disc)
        cr_admin = _class_report(db_session, admin_user.id, sample_turma, disc)

        _idr_report(
            db_session,
            chefe,
            diretor,
            sample_turma,
            disc,
            class_report_id=cr_assistente.id,
            horario_aula="08:30 às 09:30",
        )
        _idr_report(
            db_session,
            chefe,
            diretor,
            sample_turma,
            disc,
            class_report_id=cr_admin.id,
            horario_aula="09:50 às 10:50",
        )

        result = list_reports(
            data_inicio=None,
            data_fim=None,
            turma_id=None,
            diretor_imagem_id=None,
            estudio=None,
            turno=None,
            status_filtro=None,
            precisa_correcao=None,
            origem=None,
            transmissao_ou_gravada=None,
            created_by=assistant_user.id,
            professor_id=None,
            disciplina_id=None,
            sem_vinculo=False,
            sort_by="data_relatorio",
            sort_order="desc",
            limit=20,
            offset=0,
            db=db_session,
            current_user=chefe,
        )
        assert result["total"] == 1
        assert result["items"][0].class_report_id == cr_assistente.id
        assert result["items"][0].class_report_status == cr_assistente.status


class TestFinalizeRequiresProfessor:
    def test_finalizar_sem_professor_bloqueado(
        self, db_session, sample_turma, sample_professor_disciplina, assistant_user
    ):
        disc = sample_professor_disciplina["disciplina"]
        cr = _class_report(
            db_session,
            assistant_user.id,
            sample_turma,
            disc,
            professor_id=None,
            professor_nome_externo="N/A",
        )
        with pytest.raises(HTTPException) as exc:
            finalizar_relatorio(cr.id, db_session, assistant_user)
        assert exc.value.status_code == 400
        assert "professor" in exc.value.detail.lower()


class TestPdfFetchGradeReports:
    def test_ti_dia_completo_inclui_manha_e_tarde(
        self, db_session, sample_turma, sample_professor_disciplina
    ):
        chefe = _chefe_user(db_session)
        diretor = _diretor_cadastro(db_session, "Diretor PDF")
        disc = sample_professor_disciplina["disciplina"]

        sample_turma.nomenclatura_padrao = "EM 1 TI"
        sample_turma.turno = "Integral"
        db_session.commit()

        r_manha = _idr_report(
            db_session,
            chefe,
            diretor,
            sample_turma,
            disc,
            turno="Manhã",
            horario_aula="08:30 às 09:30",
            numero_aula=1,
        )
        r_tarde = _idr_report(
            db_session,
            chefe,
            diretor,
            sample_turma,
            disc,
            turno="Tarde",
            horario_aula="13:00 às 14:00",
            numero_aula=5,
            class_report_id=uuid4(),
        )

        all_grade, is_dia = _fetch_grade_reports_for_pdf(
            db_session,
            diretor.id,
            date(2026, 9, 7),
            "ESTÚDIO 1",
            turma_id=sample_turma.id,
            dia_completo=True,
        )
        assert is_dia is True
        assert len(all_grade) == 2
        ids = {r.id for r in all_grade}
        assert r_manha.id in ids
        assert r_tarde.id in ids

        # Reunião: o diretor também entrega o relatório POR TURNO no Integral.
        # A tarde sai só com as aulas da tarde, com a numeração que continua (aula 5).
        tarde, is_dia = _fetch_grade_reports_for_pdf(
            db_session,
            diretor.id,
            date(2026, 9, 7),
            "ESTÚDIO 1",
            turno="Tarde",
            turma_id=sample_turma.id,
        )
        assert is_dia is False
        assert [r.id for r in tarde] == [r_tarde.id]
        assert tarde[0].lessons[0].numero_aula == 5
        manha, _ = _fetch_grade_reports_for_pdf(
            db_session, diretor.id, date(2026, 9, 7), "ESTÚDIO 1",
            turno="Manhã", turma_id=sample_turma.id,
        )
        assert [r.id for r in manha] == [r_manha.id]

    def test_tecnico_pdf_turno_somente_do_turno_informado(
        self, db_session, sample_turma, sample_professor_disciplina
    ):
        chefe = _chefe_user(db_session)
        diretor = _diretor_cadastro(db_session, "Diretor PDF TEC")
        disc = sample_professor_disciplina["disciplina"]

        sample_turma.modalidade = "TECNICO"
        db_session.commit()

        _idr_report(
            db_session,
            chefe,
            diretor,
            sample_turma,
            disc,
            turno="Manhã",
            horario_aula="08:30 às 09:30",
        )
        _idr_report(
            db_session,
            chefe,
            diretor,
            sample_turma,
            disc,
            turno="Tarde",
            horario_aula="13:00 às 14:00",
            class_report_id=uuid4(),
        )

        manha, _ = _fetch_grade_reports_for_pdf(
            db_session,
            diretor.id,
            date(2026, 9, 7),
            "ESTÚDIO 1",
            turno="Manhã",
        )
        tarde, _ = _fetch_grade_reports_for_pdf(
            db_session,
            diretor.id,
            date(2026, 9, 7),
            "ESTÚDIO 1",
            turno="Tarde",
        )
        assert len(manha) == 1
        assert manha[0].turno == "Manhã"
        assert len(tarde) == 1
        assert tarde[0].turno == "Tarde"
