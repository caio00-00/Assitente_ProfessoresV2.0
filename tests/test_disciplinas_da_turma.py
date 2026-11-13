"""Relatório do assistente: a lista de disciplinas segue a grade da turma escolhida."""

from datetime import time

from app.models.auxiliares import Disciplina, Grade
from app.models.infraestrutura import GradeVersao
from app.models.turma import Turma

URL = "/api/v1/reports/lookup/disciplinas"


def _disc(db, nome, ativa=True):
    d = Disciplina(nome=nome, nomenclatura_padrao=nome[:3], is_active=ativa)
    db.add(d)
    db.flush()
    return d


def _slot(db, turma, disc, versao=None, hora=7):
    db.add(Grade(turma_id=turma.id, disciplina_id=disc.id if disc else None,
                 grade_versao_id=versao.id if versao else None, dia_semana=0,
                 horario_inicio=time(hora, 0), horario_fim=time(hora + 1, 0)))


def _nomes(res):
    assert res.status_code == 200, res.text
    return [d["nome"] for d in res.json()]


def test_sem_turma_lista_todas_as_ativas(client, db_session, assistant_headers):
    _disc(db_session, "MATEMÁTICA")
    _disc(db_session, "FÍSICA")
    _disc(db_session, "ANTIGA", ativa=False)
    db_session.commit()
    assert _nomes(client.get(URL, headers=assistant_headers)) == ["FÍSICA", "MATEMÁTICA"]


def test_versao_ativa_manda_e_ignora_slots_antigos(client, db_session, sample_turma, assistant_headers):
    mat, fis, qui, bio = (_disc(db_session, n) for n in ["MATEMÁTICA", "FÍSICA", "QUÍMICA", "BIOLOGIA"])
    antiga = GradeVersao(turma_id=sample_turma.id, is_active=False)
    ativa = GradeVersao(turma_id=sample_turma.id, is_active=True)
    db_session.add_all([antiga, ativa])
    db_session.flush()
    _slot(db_session, sample_turma, mat)                 # legado, sem versão
    _slot(db_session, sample_turma, fis, antiga, 8)      # versão inativa
    _slot(db_session, sample_turma, qui, ativa, 9)       # versão ativa
    _slot(db_session, sample_turma, bio, ativa, 10)
    _slot(db_session, sample_turma, bio, ativa, 11)      # repetida: aparece uma vez
    _slot(db_session, sample_turma, None, ativa, 12)     # slot sem disciplina
    db_session.commit()

    res = client.get(URL, params={"turma_id": str(sample_turma.id)}, headers=assistant_headers)
    assert _nomes(res) == ["BIOLOGIA", "QUÍMICA"]


def test_sem_versao_usa_os_slots_antigos(client, db_session, sample_turma, assistant_headers):
    mat = _disc(db_session, "MATEMÁTICA")
    _disc(db_session, "FÍSICA")
    _slot(db_session, sample_turma, mat)
    db_session.commit()
    res = client.get(URL, params={"turma_id": str(sample_turma.id)}, headers=assistant_headers)
    assert _nomes(res) == ["MATEMÁTICA"]


def test_nao_mistura_turmas_nem_traz_disciplina_inativa(client, db_session, sample_turma, assistant_headers):
    outra = Turma(nome="EM 2", modalidade="REGULAR", serie_modulo="2ª Série", turno="TARDE",
                  nomenclatura_padrao="EM 2")
    db_session.add(outra)
    db_session.flush()
    mat = _disc(db_session, "MATEMÁTICA")
    fis = _disc(db_session, "FÍSICA")
    velha = _disc(db_session, "VELHA", ativa=False)
    _slot(db_session, sample_turma, mat)
    _slot(db_session, sample_turma, velha, hora=8)
    _slot(db_session, outra, fis)
    db_session.commit()
    res = client.get(URL, params={"turma_id": str(sample_turma.id)}, headers=assistant_headers)
    assert _nomes(res) == ["MATEMÁTICA"]


def test_turma_sem_grade_devolve_vazio(client, db_session, sample_turma, assistant_headers):
    _disc(db_session, "MATEMÁTICA")
    db_session.commit()
    res = client.get(URL, params={"turma_id": str(sample_turma.id)}, headers=assistant_headers)
    assert _nomes(res) == []
