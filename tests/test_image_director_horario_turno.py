"""Horário exato por turno/modalidade, agrupamento de regulares e PDF do turno com 1 aula."""

from datetime import date, time
from types import SimpleNamespace

from app.core.security import create_access_token, get_password_hash
from app.models.auxiliares import Disciplina, Grade
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import ImageDirectorReport
from app.models.turma import Turma
from app.models.user import User
from app.services.horario_resolver import (
    get_tipo_horario,
    horarios_padrao,
    ordinal_horario,
)
from app.services.image_director_pdf import horario_exato_label
from app.services.image_director_slot import (
    list_horario_options,
    report_pertence_grade,
    resolve_slot_times,
)

SEGUNDA = date(2026, 9, 7)  # weekday() == 0


def _grade(db, turma, ini, fim, turno_aula, disc=None):
    db.add(
        Grade(
            turma_id=turma.id,
            disciplina_id=disc.id if disc else None,
            dia_semana=0,
            horario_inicio=ini,
            horario_fim=fim,
            turno_aula=turno_aula,
            canal_iptv=1,
        )
    )


def _diretor(db):
    user = User(
        email="idr_horario@test.com",
        full_name="IDR Horario",
        role="diretor_imagem",
        hashed_password=get_password_hash("x"),
        email_confirmed=True,
    )
    db.add(user)
    db.flush()
    diretor = DiretorImagem(nome="IDR Horario", user_id=user.id, is_active=True)
    db.add(diretor)
    db.commit()
    token = create_access_token(data={"sub": user.email, "role": user.role, "user_id": str(user.id)})
    return user, diretor, {"Authorization": f"Bearer {token}"}


# ── 1. Horários por turno / modalidade ──────────────────────────────────


def test_ordinal_horario():
    assert ordinal_horario("3º Horário") == 3
    assert ordinal_horario("10º horário") == 10
    assert ordinal_horario("08:30 às 09:30") is None
    assert ordinal_horario(None) is None


def test_tipo_horario_por_turno_e_modalidade():
    assert get_tipo_horario("Manhã", "EM 3 MANHÃ", "REGULAR") == "MANHA"
    assert get_tipo_horario("Tarde", "EM 3 TARDE", "REGULAR") == "TARDE"
    assert get_tipo_horario("Noite", "EM 1 NOITE", "REGULAR") == "NOITE_EM"
    assert get_tipo_horario("Noite", "EJATEC TEC ADM MOD1", "TECNICO") == "EJA"
    assert get_tipo_horario("Manhã", "EM 1 TI", "REGULAR") == "TI"
    assert get_tipo_horario("Noite", "QP ADM", "EJA") == "EJA"


def test_noite_em_tem_quinto_horario():
    ordinais = [o for o, _, _ in horarios_padrao("NOITE_EM")]
    assert ordinais[-1] == "5º Horário"


def test_resolve_slot_times_usa_grade_real_da_turma(db_session):
    turma = Turma(nome="TEC INFO", modalidade="TECNICO", serie_modulo="M1", turno="TARDE",
                  nomenclatura_padrao="TEC INFO")
    db_session.add(turma)
    db_session.commit()
    # Horários do técnico diferentes da tabela padrão da tarde
    _grade(db_session, turma, time(13, 30), time(14, 20), "TARDE")
    _grade(db_session, turma, time(14, 20), time(15, 10), "TARDE")
    db_session.commit()

    st, et = resolve_slot_times(
        db_session, turma_id=turma.id, data=SEGUNDA, turno="Tarde", horario_aula="2º Horário"
    )
    assert (st, et) == (time(14, 20), time(15, 10))


def test_resolve_slot_times_fallback_tabela_padrao(sample_turma, db_session):
    st, et = resolve_slot_times(
        db_session, turma_id=sample_turma.id, data=SEGUNDA, turno="Manhã", horario_aula="4º Horário"
    )
    assert (st, et) == (time(10, 20), time(11, 20))


def test_list_horario_options_da_grade(db_session, sample_turma):
    disc = Disciplina(nome="MATEMÁTICA", nomenclatura_padrao="MAT")
    db_session.add(disc)
    db_session.commit()
    _grade(db_session, sample_turma, time(8, 0), time(9, 0), "MANHÃ", disc)
    _grade(db_session, sample_turma, time(7, 0), time(8, 0), "MANHÃ")
    _grade(db_session, sample_turma, time(13, 0), time(14, 0), "TARDE")
    db_session.commit()

    res = list_horario_options(db_session, turma_id=sample_turma.id, data=SEGUNDA, turno="Manhã")
    assert res["fonte"] == "grade"
    assert [o["faixa"] for o in res["opcoes"]] == ["07:00 às 08:00", "08:00 às 09:00"]
    assert res["opcoes"][1]["value"] == "2º Horário"
    assert res["opcoes"][1]["disciplina_nome"] == "MATEMÁTICA"


# ── 2. Horário HH:MM no histórico / PDF ────────────────────────────────


def test_list_reports_retorna_horario_exato(client, db_session, sample_turma):
    user, diretor, headers = _diretor(db_session)
    _grade(db_session, sample_turma, time(7, 0), time(8, 0), "MANHÃ")
    _grade(db_session, sample_turma, time(8, 0), time(9, 0), "MANHÃ")
    db_session.add(
        ImageDirectorReport(
            created_by=user.id, diretor_imagem_id=diretor.id, data_relatorio=SEGUNDA,
            turno="Manhã", estudio="ESTÚDIO 1", turma_id=sample_turma.id,
            disciplina_nome="MATEMÁTICA", horario_aula="2º Horário", origem="grade",
            status="AGUARDANDO_VALIDACAO",
        )
    )
    db_session.commit()

    res = client.get("/api/v1/image-director/", headers=headers)
    assert res.status_code == 200, res.text
    item = res.json()["items"][0]
    assert item["horario_faixa"] == "08:00 às 09:00"
    assert item["start_time"].startswith("08:00")
    assert item["end_time"].startswith("09:00")
    # ── 3. regular sem ClassReport continua pertencendo à grade (agrupa por turno)
    assert item["class_report_id"] is None
    assert item["pertence_grade"] is True


def test_horario_exato_label_pdf():
    r = SimpleNamespace(horario_aula="2º Horário", start_time=time(8, 0), end_time=time(9, 0))
    assert horario_exato_label(r) == "08:00 às 09:00 (2º Horário)"
    r2 = SimpleNamespace(horario_aula="3º Horário", start_time=None, end_time=None,
                         _slot_times=(time(9, 0), time(10, 0)))
    assert horario_exato_label(r2) == "09:00 às 10:00 (3º Horário)"
    r3 = SimpleNamespace(horario_aula="GRAVAÇÃO", start_time=None, end_time=None)
    assert horario_exato_label(r3) == "GRAVAÇÃO"


# ── 3. Aula regular fora da grade não é confundida ─────────────────────


def test_report_fora_da_grade_nao_pertence(db_session, sample_turma):
    report = ImageDirectorReport(
        diretor_imagem_id=None, data_relatorio=SEGUNDA, turno="Manhã", estudio="ESTÚDIO 1",
        turma_id=sample_turma.id, horario_aula="2º Horário", origem="grade",
    )
    # Sem grade cadastrada no dia → não há como afirmar que é slot da grade
    assert report_pertence_grade(db_session, report) is False
    report.origem = "nova_aula"
    assert report_pertence_grade(db_session, report) is False


# ── 4. PDF por turno com apenas uma aula ───────────────────────────────


def test_pdf_turno_com_uma_unica_aula(client, db_session, sample_turma):
    user, diretor, headers = _diretor(db_session)
    report = ImageDirectorReport(
        created_by=user.id, diretor_imagem_id=diretor.id, data_relatorio=SEGUNDA,
        turno="Manhã", estudio="ESTÚDIO 1", turma_id=sample_turma.id,
        disciplina_nome="MATEMÁTICA", horario_aula="1º Horário", origem="nova_aula",
        status="AGUARDANDO_VALIDACAO",
    )
    db_session.add(report)
    db_session.commit()

    res = client.get(
        "/api/v1/image-director/pdf-turno",
        params={"data": "2026-09-07", "estudio": "ESTÚDIO 1", "turno": "Manhã", "report_id": str(report.id)},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"


def test_pdf_turno_grade_com_uma_aula(client, db_session, sample_turma):
    user, diretor, headers = _diretor(db_session)
    db_session.add(
        ImageDirectorReport(
            created_by=user.id, diretor_imagem_id=diretor.id, data_relatorio=SEGUNDA,
            turno="MANHÃ", estudio="ESTÚDIO 1", turma_id=sample_turma.id,
            disciplina_nome="MATEMÁTICA", horario_aula="1º Horário", origem="grade",
            status="VALIDADO",
        )
    )
    db_session.commit()
    res = client.get(
        "/api/v1/image-director/pdf-turno",
        params={"data": "2026-09-07", "estudio": "ESTÚDIO 1", "turno": "Manhã",
                "turma_id": str(sample_turma.id)},
        headers=headers,
    )
    assert res.status_code == 200, res.text


def test_pdf_turno_rascunho_unico_e_recusado(client, db_session, sample_turma):
    user, diretor, headers = _diretor(db_session)
    report = ImageDirectorReport(
        created_by=user.id, diretor_imagem_id=diretor.id, data_relatorio=SEGUNDA,
        turno="Manhã", estudio="ESTÚDIO 1", turma_id=sample_turma.id,
        horario_aula="1º Horário", origem="nova_aula", status="RASCUNHO",
    )
    db_session.add(report)
    db_session.commit()
    res = client.get(
        "/api/v1/image-director/pdf-turno",
        params={"data": "2026-09-07", "estudio": "ESTÚDIO 1", "report_id": str(report.id)},
        headers=headers,
    )
    assert res.status_code == 400


# ── Numeração conforme modalidade (TI tarde começa no 5º) ─────────────


def _turma_ti(db):
    turma = Turma(nome="EM 1 TI", modalidade="REGULAR", serie_modulo="1ª Série",
                  turno="INTEGRAL", nomenclatura_padrao="EM 1 TI")
    db.add(turma)
    db.commit()
    for ini, fim in [((7, 30), (8, 30)), ((8, 30), (9, 30)), ((9, 50), (10, 50)), ((10, 50), (11, 50)),
                     ((12, 50), (13, 50)), ((13, 50), (14, 50)), ((15, 10), (16, 10)), ((16, 10), (17, 10))]:
        _grade(db, turma, time(*ini), time(*fim), None)  # turno_aula vazio → inferido pelo horário
    db.commit()
    return turma


def test_ti_tarde_opcoes_comecam_no_quinto(db_session):
    turma = _turma_ti(db_session)
    res = list_horario_options(db_session, turma_id=turma.id, data=SEGUNDA, turno="Tarde")
    assert [o["value"] for o in res["opcoes"]] == ["5º Horário", "6º Horário", "7º Horário", "8º Horário"]
    assert res["opcoes"][0]["faixa"] == "12:50 às 13:50"
    manha = list_horario_options(db_session, turma_id=turma.id, data=SEGUNDA, turno="Manhã")
    assert [o["value"] for o in manha["opcoes"]][0] == "1º Horário"
    assert len(manha["opcoes"]) == 4


def test_ti_sem_grade_usa_padrao_do_turno(db_session):
    turma = Turma(nome="EM 2 TI", modalidade="REGULAR", serie_modulo="2ª", turno="INTEGRAL",
                  nomenclatura_padrao="EM 2 TI")
    db_session.add(turma)
    db_session.commit()
    res = list_horario_options(db_session, turma_id=turma.id, data=SEGUNDA, turno="Tarde")
    assert res["fonte"] == "padrao"
    assert [o["value"] for o in res["opcoes"]] == ["5º Horário", "6º Horário", "7º Horário", "8º Horário"]


def test_regular_tarde_reinicia_no_primeiro(db_session):
    turma = Turma(nome="EM 3 TARDE", modalidade="REGULAR", serie_modulo="3ª", turno="TARDE",
                  nomenclatura_padrao="EM 3 TARDE")
    db_session.add(turma)
    db_session.commit()
    _grade(db_session, turma, time(13, 0), time(14, 0), "TARDE")
    _grade(db_session, turma, time(14, 0), time(15, 0), "TARDE")
    db_session.commit()
    res = list_horario_options(db_session, turma_id=turma.id, data=SEGUNDA, turno="Tarde")
    assert [(o["value"], o["faixa"]) for o in res["opcoes"]] == [
        ("1º Horário", "13:00 às 14:00"),
        ("2º Horário", "14:00 às 15:00"),
    ]


def test_ti_quinto_horario_resolve_hora_certa(db_session):
    turma = _turma_ti(db_session)
    st, et = resolve_slot_times(db_session, turma_id=turma.id, data=SEGUNDA, turno="Tarde",
                                horario_aula="5º Horário")
    assert (st, et) == (time(12, 50), time(13, 50))


def test_versao_inativa_da_grade_nao_desloca_numeracao(db_session, sample_turma):
    from app.models.infraestrutura import GradeVersao

    antiga = GradeVersao(turma_id=sample_turma.id, is_active=False)
    ativa = GradeVersao(turma_id=sample_turma.id, is_active=True)
    db_session.add_all([antiga, ativa])
    db_session.commit()
    for versao, ini in [(antiga, 7), (antiga, 8), (ativa, 9), (ativa, 10)]:
        db_session.add(Grade(turma_id=sample_turma.id, grade_versao_id=versao.id, dia_semana=0,
                             horario_inicio=time(ini, 0), horario_fim=time(ini + 1, 0),
                             turno_aula="MANHÃ", canal_iptv=1))
    db_session.commit()
    res = list_horario_options(db_session, turma_id=sample_turma.id, data=SEGUNDA, turno="Manhã")
    assert [o["faixa"] for o in res["opcoes"]] == ["09:00 às 10:00", "10:00 às 11:00"]


def test_list_reports_traz_numero_da_aula_ti(client, db_session):
    turma = _turma_ti(db_session)
    user, diretor, headers = _diretor(db_session)
    db_session.add(
        ImageDirectorReport(
            created_by=user.id, diretor_imagem_id=diretor.id, data_relatorio=SEGUNDA,
            turno="Tarde", estudio="ESTÚDIO 1", turma_id=turma.id,
            horario_aula="13:50 às 14:50", origem="grade", status="VALIDADO",
        )
    )
    db_session.commit()
    item = client.get("/api/v1/image-director/", headers=headers).json()["items"][0]
    assert item["horario_ordinal"] == 6
    assert item["horario_faixa"] == "13:50 às 14:50"
    assert item["turma_ti"] is True
