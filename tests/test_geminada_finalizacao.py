"""Finalização: mesma aula lançada duas vezes x aula geminada (outro horário da mesma disciplina)."""
from datetime import date, time

import pytest
from fastapi import HTTPException

from app.api.rotas_report import finalizar_relatorio
from app.models.auxiliares import Grade
from app.models.class_report import ClassReport

QUARTA = date(2026, 10, 21)


def _slot(db, turma, disc, ini, fim):
    db.add(Grade(turma_id=turma.id, disciplina_id=disc.id, dia_semana=2, horario_inicio=ini, horario_fim=fim,
                 turno_aula="MANHÃ", canal_iptv=1, versao="Grade Base"))
    db.commit()


def _cr(db, user, turma, disc, prof, horario, ini, fim, status="RASCUNHO", conteudo="INVESTIMENTOS PARTE 03 08"):
    r = ClassReport(created_by=user.id, status=status, data_aula=QUARTA, turno="Manhã", estudio="ESTÚDIO 1",
                    turma_id=turma.id, disciplina_id=disc.id, professor_id=prof.id, horario_aula=horario,
                    start_time=ini, end_time=fim, regular="Sim", tipo_aula="Transmissão ao vivo",
                    canal_utilizado="SEDUC PI 1", conteudo_ministrado=conteudo, bncc_habilidades="X",
                    youtube_link="https://youtu.be/x", status_compliance="Pendente")
    db.add(r); db.commit(); db.refresh(r)
    return r


def test_geminada_recebe_sufixo_sozinha(admin_user, db_session, sample_turma, sample_professor_disciplina):
    prof, disc = sample_professor_disciplina["professor"], sample_professor_disciplina["disciplina"]
    _slot(db_session, sample_turma, disc, time(9, 50), time(10, 50))
    _slot(db_session, sample_turma, disc, time(10, 50), time(11, 50))
    _cr(db_session, admin_user, sample_turma, disc, prof, "3º Horário", time(9, 50), time(10, 50), status="AGUARDANDO_VALIDACAO")
    r = _cr(db_session, admin_user, sample_turma, disc, prof, "4º Horário", time(10, 50), time(11, 50))
    fin = finalizar_relatorio(report_id=r.id, db=db_session, current_user=admin_user)
    assert fin.status == "AGUARDANDO_VALIDACAO"
    assert fin.conteudo_ministrado == "INVESTIMENTOS PARTE 03 08 P2"
    assert fin.nome_ficheiro_gerado.endswith("P2.mp4")


def test_mesma_aula_duas_vezes_avisa_duplicata(admin_user, db_session, sample_turma, sample_professor_disciplina):
    prof, disc = sample_professor_disciplina["professor"], sample_professor_disciplina["disciplina"]
    _slot(db_session, sample_turma, disc, time(10, 50), time(11, 50))
    _cr(db_session, admin_user, sample_turma, disc, prof, "4º Horário", time(10, 50), time(11, 50), status="AGUARDANDO_VALIDACAO")
    r = _cr(db_session, admin_user, sample_turma, disc, prof, "4º Horário", time(10, 50), time(11, 50))
    with pytest.raises(HTTPException) as exc:
        finalizar_relatorio(report_id=r.id, db=db_session, current_user=admin_user)
    assert exc.value.status_code == 409
    assert "duplicata" in exc.value.detail and "geminada" not in exc.value.detail.lower()
