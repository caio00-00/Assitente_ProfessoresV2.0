"""Tests for Image Director report slot identity and lesson numbering."""

from datetime import date, time
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.core.security import create_access_token, get_password_hash
from app.models.auxiliares import Disciplina, Grade
from app.models.diretor_imagem import DiretorImagem
from app.models.user import User
from app.schemas.image_director_report import ImageDirectorReportCreate
from app.services.image_director_slot import (
    compute_numero_aula_slot,
    find_existing_report_by_slot,
)


def _diretor_user(db_session):
    user = User(
        email="idr_slot@test.com",
        full_name="IDR Slot Test",
        role="diretor_imagem",
        hashed_password=get_password_hash("test123"),
        email_confirmed=True,
    )
    db_session.add(user)
    db_session.flush()
    diretor = DiretorImagem(nome="IDR Slot Test", user_id=user.id, is_active=True)
    db_session.add(diretor)
    db_session.commit()
    return user, diretor


def _create_report(db_session, user, diretor, sample_turma, disc, **extra):
    from app.api.rotas_diretor_imagem import create_report

    base = {
        "diretor_imagem_id": diretor.id,
        "data_relatorio": date(2026, 9, 7),
        "turno": "Manhã",
        "estudio": "ESTÚDIO 1",
        "turma_id": sample_turma.id,
        "disciplina_id": disc.id,
        "disciplina_nome": "MATEMÁTICA",
        "professor_nome_externo": "Prof A",
        "horario_aula": "08:30 às 09:30",
        "class_report_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "origem": "grade",
    }
    base.update(extra)
    payload = ImageDirectorReportCreate(**base)
    return create_report(payload, db_session, user)


def test_lookup_existing_by_class_report_id(db_session, sample_turma):
    from app.api.rotas_diretor_imagem import lookup_existing_report

    user, diretor = _diretor_user(db_session)
    disc = Disciplina(nome="MATEMÁTICA", nomenclatura_padrao="MAT")
    db_session.add(disc)
    db_session.commit()

    created = _create_report(db_session, user, diretor, sample_turma, disc)
    lookup = lookup_existing_report(
        data=date(2026, 9, 7),
        turno="Manhã",
        estudio="ESTÚDIO 1",
        disciplina_id=None,
        diretor_imagem_id=diretor.id,
        class_report_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        turma_id=None,
        horario_aula=None,
        db=db_session,
        current_user=user,
    )
    assert lookup is not None
    assert lookup.id == str(created.id)


def test_two_slots_same_disciplina_different_reports(db_session, sample_turma):
    user, diretor = _diretor_user(db_session)
    disc = Disciplina(nome="MATEMÁTICA", nomenclatura_padrao="MAT")
    db_session.add(disc)
    db_session.commit()

    r1 = _create_report(
        db_session,
        user,
        diretor,
        sample_turma,
        disc,
        horario_aula="08:30 às 09:30",
        class_report_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    )
    r2 = _create_report(
        db_session,
        user,
        diretor,
        sample_turma,
        disc,
        horario_aula="09:50 às 10:50",
        class_report_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
    )
    assert r1.id != r2.id


def test_duplicate_slot_returns_409(db_session, sample_turma):
    user, diretor = _diretor_user(db_session)
    disc = Disciplina(nome="MATEMÁTICA", nomenclatura_padrao="MAT")
    db_session.add(disc)
    db_session.commit()

    _create_report(db_session, user, diretor, sample_turma, disc)
    with pytest.raises(HTTPException) as exc:
        _create_report(db_session, user, diretor, sample_turma, disc)
    assert exc.value.status_code == 409


def test_find_existing_by_horario(db_session, sample_turma):
    user, diretor = _diretor_user(db_session)
    disc = Disciplina(nome="MATEMÁTICA", nomenclatura_padrao="MAT")
    db_session.add(disc)
    db_session.commit()

    created = _create_report(
        db_session,
        user,
        diretor,
        sample_turma,
        disc,
        horario_aula="08:30 às 09:30",
        class_report_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
    )
    found = find_existing_report_by_slot(
        db_session,
        diretor.id,
        date(2026, 9, 7),
        "Manhã",
        "ESTÚDIO 1",
        turma_id=sample_turma.id,
        horario_aula="08:30 às 09:30",
    )
    assert found is not None
    assert found.id == created.id


def test_numero_aula_regular_morning(db_session, sample_turma):
    from app.api.rotas_diretor_imagem import lookup_numero_aula

    user, _ = _diretor_user(db_session)
    data = date(2026, 9, 7)
    assert data.weekday() == 0

    db_session.add(
        Grade(
            turma_id=sample_turma.id,
            dia_semana=0,
            horario_inicio=time(8, 30),
            horario_fim=time(9, 30),
            turno_aula="MANHÃ",
            canal_iptv=1,
        )
    )
    db_session.add(
        Grade(
            turma_id=sample_turma.id,
            dia_semana=0,
            horario_inicio=time(9, 50),
            horario_fim=time(10, 50),
            turno_aula="MANHÃ",
            canal_iptv=1,
        )
    )
    db_session.commit()

    n1 = compute_numero_aula_slot(
        db_session, sample_turma.id, data, horario_aula="08:30 às 09:30", report_turno="Manhã"
    )
    n2 = compute_numero_aula_slot(
        db_session, sample_turma.id, data, horario_aula="09:50 às 10:50", report_turno="Manhã"
    )
    assert n1 == 1
    assert n2 == 2

    api = lookup_numero_aula(
        turma_id=sample_turma.id,
        data=data,
        horario_aula="09:50 às 10:50",
        class_report_id=None,
        turno="Manhã",
        db=db_session,
        current_user=user,
    )
    assert api.numero_aula == 2


def test_is_ti_turma_nao_confunde_tim_com_ti(db_session, sample_turma):
    """Turmas 'TIM' (manhã) não devem ser tratadas como Tempo Integral."""
    from app.services.image_director_slot import _is_ti_turma

    sample_turma.nomenclatura_padrao = "EM 1 TIM"
    sample_turma.turno = "MANHÃ"
    db_session.commit()
    assert _is_ti_turma(sample_turma) is False

    sample_turma.nomenclatura_padrao = "EM 1 TI"
    sample_turma.turno = "Integral"
    db_session.commit()
    assert _is_ti_turma(sample_turma) is True


def test_numero_aula_tecnico_per_turno(db_session, sample_turma):
    """TECNICO: numeração reinicia em cada turno (PDF por turno)."""
    sample_turma.modalidade = "TECNICO"
    db_session.commit()

    data = date(2026, 9, 7)
    assert data.weekday() == 0
    db_session.add(
        Grade(
            turma_id=sample_turma.id,
            dia_semana=0,
            horario_inicio=time(8, 30),
            horario_fim=time(9, 30),
            turno_aula="MANHÃ",
            canal_iptv=1,
        )
    )
    db_session.add(
        Grade(
            turma_id=sample_turma.id,
            dia_semana=0,
            horario_inicio=time(13, 0),
            horario_fim=time(14, 0),
            turno_aula="TARDE",
            canal_iptv=1,
        )
    )
    db_session.commit()

    n_manha = compute_numero_aula_slot(
        db_session, sample_turma.id, data, horario_aula="08:30 às 09:30", report_turno="Manhã"
    )
    n_tarde = compute_numero_aula_slot(
        db_session, sample_turma.id, data, horario_aula="13:00 às 14:00", report_turno="Tarde"
    )
    assert n_manha == 1
    assert n_tarde == 1


def test_numero_aula_ti_continuous(db_session, sample_turma):
    """TI: tarde continua a sequência da manhã (ex.: manhã 1–4, tarde 5)."""
    sample_turma.nomenclatura_padrao = "EM 1 TI"
    sample_turma.turno = "Integral"
    db_session.commit()

    data = date(2026, 9, 7)
    assert data.weekday() == 0
    morning_times = [
        (time(7, 30), time(8, 30)),
        (time(8, 30), time(9, 30)),
        (time(9, 50), time(10, 50)),
        (time(10, 50), time(11, 50)),
    ]
    for h_ini, h_fim in morning_times:
        db_session.add(
            Grade(
                turma_id=sample_turma.id,
                dia_semana=0,
                horario_inicio=h_ini,
                horario_fim=h_fim,
                turno_aula="MANHÃ",
                canal_iptv=1,
            )
        )
    db_session.add(
        Grade(
            turma_id=sample_turma.id,
            dia_semana=0,
            horario_inicio=time(12, 50),
            horario_fim=time(13, 50),
            turno_aula="TARDE",
            canal_iptv=1,
        )
    )
    db_session.commit()

    n_manha_1 = compute_numero_aula_slot(
        db_session, sample_turma.id, data, horario_aula="07:30 às 08:30", report_turno="Manhã"
    )
    n_manha_4 = compute_numero_aula_slot(
        db_session, sample_turma.id, data, horario_aula="10:50 às 11:50", report_turno="Manhã"
    )
    n_tarde_1 = compute_numero_aula_slot(
        db_session, sample_turma.id, data, horario_aula="12:50 às 13:50", report_turno="Tarde"
    )
    assert n_manha_1 == 1
    assert n_manha_4 == 4
    assert n_tarde_1 == 5


def test_numero_aula_tarde_parcial_reinicia(db_session, sample_turma):
    """Turma só tarde: inicia em Aula 01."""
    sample_turma.turno = "TARDE"
    sample_turma.nomenclatura_padrao = "EM 2 TARDE"
    db_session.commit()

    data = date(2026, 9, 7)
    db_session.add(
        Grade(
            turma_id=sample_turma.id,
            dia_semana=0,
            horario_inicio=time(13, 0),
            horario_fim=time(14, 0),
            turno_aula="TARDE",
            canal_iptv=1,
        )
    )
    db_session.add(
        Grade(
            turma_id=sample_turma.id,
            dia_semana=0,
            horario_inicio=time(14, 0),
            horario_fim=time(15, 0),
            turno_aula="TARDE",
            canal_iptv=1,
        )
    )
    db_session.commit()

    n1 = compute_numero_aula_slot(
        db_session, sample_turma.id, data, horario_aula="13:00 às 14:00", report_turno="Tarde"
    )
    n2 = compute_numero_aula_slot(
        db_session, sample_turma.id, data, horario_aula="14:00 às 15:00", report_turno="Tarde"
    )
    assert n1 == 1
    assert n2 == 2
