"""Nº do horário pela tabela oficial: dia sem a 1ª aula não desloca a numeração."""

from datetime import date, time

from app.models.auxiliares import Disciplina, Grade
from app.models.turma import Turma
from app.services.image_director_slot import (
    compute_numero_aula_slot, list_horario_options, report_pertence_grade, resolve_slot_ordinal, resolve_slot_times,
)

SEXTA = date(2026, 10, 9)  # sexta-feira (dia_semana 4)


def _turma(db, turno="INTEGRAL", nomen="EPT ESTUDIO 6 TI", modalidade="TECNICO"):
    t = Turma(nome=nomen, modalidade=modalidade, serie_modulo="-", turno=turno, nomenclatura_padrao=nomen)
    db.add(t)
    db.flush()
    return t


def _slots(db, turma, horarios, dia=4):
    d = Disciplina(nome=f"DISC {turma.nome}")
    db.add(d)
    db.flush()
    for ini, fim in horarios:
        db.add(Grade(turma_id=turma.id, disciplina_id=d.id, dia_semana=dia,
                     horario_inicio=time(*ini), horario_fim=time(*fim)))
    db.commit()


def test_integral_sem_a_primeira_aula_nao_desloca(db_session):
    # Sexta da EPT (integral): começa 08:30, sem o 1º horário (07:30)
    t = _turma(db_session)
    _slots(db_session, t, [((8, 30), (9, 30)), ((9, 50), (10, 50)), ((10, 50), (11, 50)),
                           ((12, 50), (13, 50)), ((13, 50), (14, 50))])
    ops = list_horario_options(db_session, turma_id=t.id, data=SEXTA, turno=None)["opcoes"]
    assert [(o["value"], o["inicio"]) for o in ops] == [
        ("2º Horário", "08:30"), ("3º Horário", "09:50"), ("4º Horário", "10:50"),
        ("5º Horário", "12:50"), ("6º Horário", "13:50")]
    # O caso do relato: 3º horário = 09:50 às 10:50 (antes dava 10:50 às 11:50)
    assert resolve_slot_times(db_session, turma_id=t.id, data=SEXTA, turno="MANHÃ",
                              horario_aula="3º Horário") == (time(9, 50), time(10, 50))
    # 4º horário é de manhã (10:50), não a aula da tarde
    assert resolve_slot_times(db_session, turma_id=t.id, data=SEXTA, turno="MANHÃ",
                              horario_aula="4º Horário") == (time(10, 50), time(11, 50))
    assert resolve_slot_ordinal(db_session, turma_id=t.id, data=SEXTA, turno="MANHÃ",
                                horario_aula=None, start_time=time(8, 30)) == 2
    assert compute_numero_aula_slot(db_session, t.id, SEXTA, horario_aula="4º Horário") == 4
    # Tarde do integral: só 5º e 6º
    tarde = list_horario_options(db_session, turma_id=t.id, data=SEXTA, turno="TARDE")["opcoes"]
    assert [o["value"] for o in tarde] == ["5º Horário", "6º Horário"]


def test_regular_manha_sem_o_primeiro_horario(db_session):
    t = _turma(db_session, turno="MANHÃ", nomen="1ª SÉRIE MANHÃ", modalidade="REGULAR")
    _slots(db_session, t, [((8, 0), (9, 0)), ((9, 0), (10, 0)), ((10, 20), (11, 20))])
    ops = list_horario_options(db_session, turma_id=t.id, data=SEXTA, turno="MANHÃ")["opcoes"]
    assert [o["value"] for o in ops] == ["2º Horário", "3º Horário", "4º Horário"]
    assert resolve_slot_times(db_session, turma_id=t.id, data=SEXTA, turno="MANHÃ",
                              horario_aula="2º Horário") == (time(8, 0), time(9, 0))


def test_grade_com_horarios_proprios_continua_em_sequencia(db_session):
    # Horários fora da tabela oficial: numeração segue a ordem do dia
    t = _turma(db_session, turno="NOITE", nomen="TEC NOITE", modalidade="TECNICO")
    _slots(db_session, t, [((19, 5), (19, 50)), ((19, 50), (20, 35)), ((20, 50), (21, 35))])
    ops = list_horario_options(db_session, turma_id=t.id, data=SEXTA, turno="NOITE")["opcoes"]
    assert [o["value"] for o in ops] == ["1º Horário", "2º Horário", "3º Horário"]


def test_dia_completo_continua_igual(db_session):
    t = _turma(db_session)
    _slots(db_session, t, [((7, 30), (8, 30)), ((8, 30), (9, 30)), ((9, 50), (10, 50)), ((10, 50), (11, 50))])
    ops = list_horario_options(db_session, turma_id=t.id, data=SEXTA, turno="MANHÃ")["opcoes"]
    assert [(o["value"], o["inicio"]) for o in ops] == [
        ("1º Horário", "07:30"), ("2º Horário", "08:30"), ("3º Horário", "09:50"), ("4º Horário", "10:50")]
