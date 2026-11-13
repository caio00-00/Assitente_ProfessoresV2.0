"""
Canal Educação v5 — A Aula: geração pela grade e pela agenda, ligação com os
relatórios, status, API e telas.
"""

import uuid
from datetime import date, time, timedelta

import pytest

from app.models import aula as A
from app.models.agenda_estudio import AgendamentoEstudio
from app.models.auxiliares import Grade
from app.models.class_report import ClassReport
from app.models.image_director_report import ImageDirectorLesson, ImageDirectorReport
from app.models.infraestrutura import Estudio
from app.modulos.aulas import servico

SEGUNDA = date(2026, 10, 19)  # dia_semana = 0


@pytest.fixture
def estudio(db_session):
    e = Estudio(nome="Estúdio V5", horario_inicio=time(7, 0), horario_fim=time(22, 0), ativo=True)
    db_session.add(e)
    db_session.commit()
    return e


@pytest.fixture
def slot(db_session, sample_turma, sample_professor_disciplina, estudio):
    g = Grade(turma_id=sample_turma.id, disciplina_id=sample_professor_disciplina["disciplina"].id,
              professor_id=sample_professor_disciplina["professor"].id, estudio_id=estudio.id,
              dia_semana=0, horario_inicio=time(8, 0), horario_fim=time(9, 0), turno_aula="MANHÃ", canal_iptv=1)
    db_session.add(g)
    db_session.commit()
    return g


def _cr(db, turma, pd, autor, status="RASCUNHO", dia=SEGUNDA, horario="08:00 às 09:00", **extra):
    cr = ClassReport(
        id=uuid.uuid4(), created_by=autor, status=status, data_aula=dia, turno="Manhã",
        estudio="Estúdio V5", turma_id=turma.id, disciplina_id=pd["disciplina"].id,
        professor_id=pd["professor"].id, horario_aula=horario, regular="Sim",
        tipo_aula="Transmissão ao vivo", canal_utilizado="1", conteudo_ministrado="X",
        status_compliance="Pendente", **extra,
    )
    db.add(cr)
    db.commit()
    return cr


def _aulas(db, dia=SEGUNDA):
    return db.query(A.Aula).filter(A.Aula.data == dia).all()


# ─── Status ──────────────────────────────────────────────────────────

class _R:
    def __init__(self, status, precisa_correcao=False):
        self.status, self.precisa_correcao = status, precisa_correcao


def _a(dia=SEGUNDA, cancelada=False):
    return A.Aula(data=dia, cancelada_na_agenda=cancelada)


@pytest.mark.parametrize("cr,idr,esperado", [
    (None, None, A.SEM_RELATORIO),
    (_R("RASCUNHO"), None, A.EM_RELATORIO),
    (_R("RASCUNHO", True), None, A.DEVOLVIDA),
    (_R("AGUARDANDO_VALIDACAO"), None, A.AGUARDANDO_VALIDACAO),
    (_R("FINALIZADO"), None, A.AGUARDANDO_VALIDACAO),
    (_R("VALIDADO"), _R("AGUARDANDO_VALIDACAO"), A.AGUARDANDO_IMAGEM),
    (_R("VALIDADO"), _R("VALIDADO"), A.VALIDADA),
    (_R("VALIDADO"), None, A.VALIDADA),
    (_R("CANCELADO"), None, A.CANCELADA),
])
def test_status_da_aula(cr, idr, esperado):
    assert servico.calcular_status(_a(), cr, idr, hoje=SEGUNDA + timedelta(days=1)) == esperado


def test_aula_futura_sem_relatorio_e_prevista():
    assert servico.calcular_status(_a(), None, None, hoje=SEGUNDA) == A.PREVISTA


def test_cancelada_na_agenda_sem_relatorio():
    assert servico.calcular_status(_a(cancelada=True), None, None, hoje=SEGUNDA) == A.CANCELADA


# ─── Geração e ligação ───────────────────────────────────────────────

def test_grade_gera_aula_e_nao_recalcula_sem_mudanca(db_session, slot):
    assert servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA) == 1
    aulas = _aulas(db_session)
    assert len(aulas) == 1 and aulas[0].grade_id == slot.id and aulas[0].origem == A.ORIGEM_GRADE
    assert servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA) == 0


def test_relatorio_liga_na_aula_e_muda_o_status(db_session, slot, sample_turma, sample_professor_disciplina, admin_user):
    servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA)
    cr = _cr(db_session, sample_turma, sample_professor_disciplina, admin_user.id)
    assert servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA) == 1  # o relatório mudou a assinatura
    (aula,) = _aulas(db_session)
    assert aula.class_report_id == cr.id and aula.status == A.EM_RELATORIO

    cr.status = "AGUARDANDO_VALIDACAO"
    db_session.commit()
    servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA)
    db_session.refresh(aula)
    assert aula.status == A.AGUARDANDO_VALIDACAO


def test_relatorio_sem_aula_prevista_vira_aula_propria(db_session, slot, sample_turma, sample_professor_disciplina, admin_user):
    terca = SEGUNDA + timedelta(days=1)  # a grade não tem aula na terça
    cr = _cr(db_session, sample_turma, sample_professor_disciplina, admin_user.id, dia=terca)
    servico.sincronizar_periodo(db_session, terca, terca)
    (aula,) = _aulas(db_session, terca)
    assert aula.origem == A.ORIGEM_RELATORIO and aula.class_report_id == cr.id


def test_dois_relatorios_para_a_mesma_aula(db_session, slot, sample_turma, sample_professor_disciplina, admin_user):
    _cr(db_session, sample_turma, sample_professor_disciplina, admin_user.id)
    _cr(db_session, sample_turma, sample_professor_disciplina, admin_user.id)
    servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA)
    aulas = _aulas(db_session)
    assert sorted(a.origem for a in aulas) == [A.ORIGEM_GRADE, A.ORIGEM_RELATORIO]
    assert len({a.class_report_id for a in aulas}) == 2  # nenhum relatório em duas aulas


def test_aula_que_sai_da_grade_com_relatorio_fica(db_session, slot, sample_turma, sample_professor_disciplina, admin_user):
    cr = _cr(db_session, sample_turma, sample_professor_disciplina, admin_user.id)
    servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA)
    db_session.delete(slot)
    db_session.commit()
    servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA, forcar=True)
    (aula,) = _aulas(db_session)
    assert aula.class_report_id == cr.id  # o relatório nunca fica sem aula


def test_aula_sem_relatorio_que_sai_da_grade_some(db_session, slot):
    servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA)
    db_session.delete(slot)
    db_session.commit()
    servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA, forcar=True)
    assert _aulas(db_session) == []


def test_cancelamento_na_agenda(db_session, slot, estudio):
    db_session.add(AgendamentoEstudio(data=SEGUNDA, estudio_id=estudio.id, horario_inicio=time(8, 0),
                                      horario_fim=time(9, 0), tipo="AULA_CANCELADA", titulo="Cancelada",
                                      descricao="Professor doente", grade_id=slot.id))
    db_session.commit()
    servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA)
    (aula,) = _aulas(db_session)
    assert aula.status == A.CANCELADA and aula.motivo_cancelamento == "Professor doente"


def test_gravacao_da_agenda_vira_aula(db_session, sample_turma, estudio):
    db_session.add(AgendamentoEstudio(data=SEGUNDA, estudio_id=estudio.id, horario_inicio=time(14, 0),
                                      horario_fim=time(15, 0), tipo="GRAVACAO", titulo="Gravação",
                                      turma_id=sample_turma.id))
    db_session.commit()
    servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA)
    (aula,) = _aulas(db_session)
    assert aula.origem == A.ORIGEM_AGENDA and aula.tipo == "gravacao"


def test_relatorio_de_imagem_pela_aula_do_turno(db_session, slot, sample_turma, sample_professor_disciplina, admin_user):
    cr = _cr(db_session, sample_turma, sample_professor_disciplina, admin_user.id, status="VALIDADO")
    from app.models.diretor_imagem import DiretorImagem
    d = DiretorImagem(id=uuid.uuid4(), nome="Diretor Teste V5", is_active=True)
    db_session.add(d)
    db_session.flush()
    idr = ImageDirectorReport(id=uuid.uuid4(), created_by=admin_user.id, status="AGUARDANDO_VALIDACAO",
                              diretor_imagem_id=d.id,
                              data_relatorio=SEGUNDA, turno="Manhã", estudio="Estúdio V5")
    db_session.add(idr)
    db_session.flush()
    db_session.add(ImageDirectorLesson(id=uuid.uuid4(), report_id=idr.id, numero_aula=1, class_report_id=cr.id,
                                       disciplina_nome="X", professor_nome="Y", transmissao_ou_gravada="Transmissão"))
    db_session.commit()
    servico.sincronizar_periodo(db_session, SEGUNDA, SEGUNDA)
    (aula,) = _aulas(db_session)
    assert aula.image_director_report_id == idr.id and aula.status == A.AGUARDANDO_IMAGEM
    assert aula.cobrar.startswith("Pendente")


# ─── API e telas ─────────────────────────────────────────────────────

def test_api_lista_e_resumo(client, admin_headers, slot):
    r = client.get(f"/api/v1/aulas?inicio={SEGUNDA}&fim={SEGUNDA}", headers=admin_headers)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["resumo"]["total"] == 1 and corpo["aulas"][0]["disciplina"]


def test_api_periodo_grande_demais(client, admin_headers):
    r = client.get(f"/api/v1/aulas?inicio={SEGUNDA}&fim={SEGUNDA + timedelta(days=90)}", headers=admin_headers)
    assert r.status_code == 422


def test_api_exige_login(client):
    assert client.get("/api/v1/aulas").status_code == 401


def test_linha_do_tempo_v4_continua_respondendo(client, admin_headers):
    # /api/v1/aulas/linha-do-tempo (v4) não pode ser engolida por /api/v1/aulas/{id}
    r = client.get("/api/v1/aulas/linha-do-tempo", headers=admin_headers)
    assert r.status_code == 422 and "Informe" in r.text


def test_fragmentos_e_paginas(client, admin_headers, slot):
    lista = client.get(f"/parciais/aulas?inicio={SEGUNDA}&fim={SEGUNDA}&turma_id=&estudio_id=&status=&q=",
                       headers=admin_headers)
    assert lista.status_code == 200 and "Segunda, 19 de outubro" in lista.text
    aula_id = client.get(f"/api/v1/aulas?inicio={SEGUNDA}&fim={SEGUNDA}", headers=admin_headers).json()["aulas"][0]["id"]
    det = client.get(f"/parciais/aulas/{aula_id}", headers=admin_headers)
    assert det.status_code == 200 and "Fazer o relatório desta aula" in det.text
    assert client.get("/parciais/aulas/agora", headers=admin_headers).status_code == 200
    assert client.get("/aulas").status_code == 200
    assert client.get("/aulas/agora").status_code == 200


def test_diretor_ve_o_botao_do_relatorio_de_imagem(client, db_session, slot):
    from app.core.security import create_access_token, get_password_hash
    from app.models.user import User

    u = User(id=uuid.uuid4(), email="dir.v5@test.com", full_name="Diretor V5", role="diretor_imagem",
             hashed_password=get_password_hash("x12345678"), is_active=True, email_confirmed=True)
    db_session.add(u)
    db_session.commit()
    h = {"Authorization": f"Bearer {create_access_token({'sub': u.email, 'role': u.role, 'user_id': str(u.id)})}"}
    r = client.get(f"/api/v1/aulas?inicio={SEGUNDA}&fim={SEGUNDA}", headers=h)
    assert r.status_code == 200, r.text
    aula_id = r.json()["aulas"][0]["id"]
    det = client.get(f"/parciais/aulas/{aula_id}", headers=h).text
    assert "Fazer o relatório de imagem do turno" in det
    assert "Fazer o relatório desta aula" not in det
