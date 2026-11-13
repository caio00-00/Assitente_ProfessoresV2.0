"""Agenda de Estúdios — substitui a planilha de agendamento (Admin / Diretor-Chefe)."""

from datetime import date, time, timedelta
from io import BytesIO

from openpyxl import load_workbook

import uuid

from app.core.security import create_access_token, get_password_hash
from app.models.auxiliares import Disciplina, Grade, Professor
from app.models.class_report import ClassReport
from app.models.image_director_report import ImageDirectorReport
from app.models.diretor_imagem import DiretorImagem
from app.models.infraestrutura import Estudio, GradeVersao
from app.models.turma import Turma
from app.models.user import User

QUARTA = date(2026, 8, 5)  # quarta-feira (dia_semana 2)
URL = "/api/v1/agenda-estudios"


def _headers(db, role, email):
    u = User(email=email, full_name=role, role=role, hashed_password=get_password_hash("x"), email_confirmed=True)
    db.add(u)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(data={'sub': u.email, 'role': u.role, 'user_id': str(u.id)})}"}


def _cenario(db):
    e1 = Estudio(nome="Estúdio 01", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    e2 = Estudio(nome="Estúdio 02", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    inativo = Estudio(nome="Estúdio 99", horario_inicio=time(6, 0), horario_fim=time(23, 0), ativo=False)
    db.add_all([e1, e2, inativo])
    turma = Turma(nome="1ª Série Integral", modalidade="REGULAR", serie_modulo="1ª Série",
                  turno="INTEGRAL", nomenclatura_padrao="EM 1 TI")
    turma_off = Turma(nome="Antiga", modalidade="REGULAR", serie_modulo="1", turno="MANHÃ",
                      nomenclatura_padrao="OLD", is_active=False)
    fis = Disciplina(nome="FÍSICA")
    mat = Disciplina(nome="MATEMÁTICA")
    prof = Professor(nome="Prof. Física")
    db.add_all([turma, turma_off, fis, mat, prof])
    db.flush()
    db.add_all([
        # quarta, manhã, Estúdio 01
        Grade(turma_id=turma.id, disciplina_id=fis.id, professor_id=prof.id, estudio_id=e1.id,
              dia_semana=2, horario_inicio=time(7, 30), horario_fim=time(8, 30)),
        Grade(turma_id=turma.id, disciplina_id=mat.id, estudio_id=e1.id,
              dia_semana=2, horario_inicio=time(8, 30), horario_fim=time(9, 30)),
        # quarta, tarde, Estúdio 01
        Grade(turma_id=turma.id, disciplina_id=mat.id, estudio_id=e1.id,
              dia_semana=2, horario_inicio=time(12, 50), horario_fim=time(13, 50)),
        # outra dia da semana — não aparece na quarta
        Grade(turma_id=turma.id, disciplina_id=fis.id, estudio_id=e1.id,
              dia_semana=3, horario_inicio=time(7, 30), horario_fim=time(8, 30)),
        # turma inativa — não aparece
        Grade(turma_id=turma_off.id, disciplina_id=fis.id, estudio_id=e2.id,
              dia_semana=2, horario_inicio=time(7, 30), horario_fim=time(8, 30)),
        # gravação sem horário (00:00)
        Grade(turma_id=turma.id, disciplina_id=fis.id, estudio_id=e2.id,
              dia_semana=2, horario_inicio=time(0, 0), horario_fim=time(0, 30)),
    ])
    versao_inativa = GradeVersao(turma_id=turma.id, is_active=False)
    db.add(versao_inativa)
    db.flush()
    db.add(Grade(turma_id=turma.id, grade_versao_id=versao_inativa.id, disciplina_id=mat.id,
                 estudio_id=e2.id, dia_semana=2, horario_inicio=time(9, 50), horario_fim=time(10, 50)))
    d1 = DiretorImagem(nome="MAYOLLY")
    d2 = DiretorImagem(nome="FLAVILTON")
    db.add_all([d1, d2])
    db.commit()
    return {"e1": e1.id, "e2": e2.id, "turma": str(turma.id), "d1": str(d1.id), "d2": str(d2.id)}


def _coluna(agenda, turno, estudio_id):
    t = next(t for t in agenda["turnos"] if t["turno"] == turno)
    return next(c for c in t["estudios"] if c["estudio_id"] == estudio_id)


def test_acesso_edita_so_admin_e_chefe_pedagogico_so_visualiza(client, db_session, admin_headers, assistant_headers):
    chefe = _headers(db_session, "diretor_chefe", "chefe@test.com")
    diretor = _headers(db_session, "diretor_imagem", "dir@test.com")
    gestor = _headers(db_session, "gestor", "gestor@test.com")
    coord = _headers(db_session, "coordenador", "coord@test.com")
    assert client.get(f"{URL}/opcoes", headers=admin_headers).json()["pode_editar"] is True
    assert client.get(f"{URL}/opcoes", headers=chefe).json()["pode_editar"] is True
    # Pedagógico: vê a disponibilidade, não agenda
    for h in (gestor, coord):
        assert client.get(f"{URL}/opcoes", headers=h).json()["pode_editar"] is False
        assert client.get(f"{URL}/dia", headers=h).status_code == 200
        r = client.post(f"{URL}/agendamentos", json={"data": QUARTA.isoformat(), "estudio_id": 1,
                                                     "horario_inicio": "10:00", "horario_fim": "11:00",
                                                     "tipo": "EVENTO", "titulo": "x"}, headers=h)
        assert r.status_code == 403
        assert client.post(f"{URL}/feriados", json={"data": QUARTA.isoformat(), "nome": "x"},
                           headers=h).status_code == 403
    # Diretor de imagem e assistente: sem acesso (grade igual à do assistente)
    for h in (diretor, assistant_headers):
        assert client.get(f"{URL}/dia", headers=h).status_code == 403
    assert client.get("/agenda-estudios").status_code == 200


def test_dia_montado_a_partir_da_grade(client, db_session, admin_headers):
    ids = _cenario(db_session)
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    assert agenda["dia_semana_label"] == "Quarta-feira"
    assert [e["estudio_nome"] for e in agenda["turnos"][0]["estudios"]] == ["Estúdio 01", "Estúdio 02"]

    manha = _coluna(agenda, "manha", ids["e1"])
    assert [(i["inicio"], i["titulo"]) for i in manha["itens"]] == [("07:30", "FÍSICA"), ("08:30", "MATEMÁTICA")]
    assert manha["itens"][0]["professor"] == "Prof. Física"
    assert manha["itens"][0]["ordinal"] == "1º Horário"
    assert manha["turmas"] == ["EM 1 TI"]
    assert [i["inicio"] for i in _coluna(agenda, "tarde", ids["e1"])["itens"]] == ["12:50"]
    # turma inativa e versão de grade inativa ficam de fora
    assert _coluna(agenda, "manha", ids["e2"])["itens"] == []
    assert [g["disciplina"] for g in agenda["gravacoes_sem_horario"]] == ["FÍSICA"]
    assert agenda["resumo"]["aulas"] == 3
    assert agenda["resumo"]["estudios_sem_diretor"] == 2  # E1 manhã e tarde em uso, sem escala


def test_escala_diaria_de_diretores(client, db_session, admin_headers):
    ids = _cenario(db_session)
    dia = {"data": QUARTA.isoformat(), "turno": "manha", "estudio_id": ids["e1"]}
    r = client.put(f"{URL}/escala-dia", json={**dia, "diretor_imagem_id": ids["d1"]}, headers=admin_headers)
    assert r.status_code == 200
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    assert _coluna(agenda, "manha", ids["e1"])["diretor"]["nome"] == "MAYOLLY"
    assert agenda["resumo"]["estudios_sem_diretor"] == 1  # a tarde do E1 ficou sem ninguém
    # A escala vale só para o dia: na quarta seguinte não há diretor (não existe escala fixa)
    prox = client.get(f"{URL}/dia", params={"data": "2026-08-12"}, headers=admin_headers).json()
    assert _coluna(prox, "manha", ids["e1"])["diretor"] is None
    assert client.get(f"{URL}/escala-dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()[0][
        "diretor_imagem_id"] == ids["d1"]

    # Copiar a quarta para quinta, sexta e para um feriado (ignorado)
    client.post(f"{URL}/feriados", json={"data": "2026-08-07", "nome": "Feriado"}, headers=admin_headers)
    r = client.post(f"{URL}/escala-dia/copiar", json={"de_data": QUARTA.isoformat(),
                                                      "para_datas": ["2026-08-06", "2026-08-07", "2026-08-12"]},
                    headers=admin_headers)
    assert r.json() == {"dias": ["2026-08-06", "2026-08-12"], "feriados_ignorados": ["2026-08-07"]}
    prox = client.get(f"{URL}/dia", params={"data": "2026-08-12"}, headers=admin_headers).json()
    assert _coluna(prox, "manha", ids["e1"])["diretor"]["nome"] == "MAYOLLY"

    # Sem diretor: tira da escala do dia
    client.put(f"{URL}/escala-dia", json={**dia, "diretor_imagem_id": None}, headers=admin_headers)
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    assert _coluna(agenda, "manha", ids["e1"])["diretor"] is None
    assert client.post(f"{URL}/escala-dia/copiar", json={"de_data": QUARTA.isoformat(), "para_datas": ["2026-08-13"]},
                       headers=admin_headers).status_code == 422  # origem vazia


def test_agendamento_com_conflito_de_aula_e_de_agendamento(client, db_session, admin_headers):
    ids = _cenario(db_session)
    base = {"data": QUARTA.isoformat(), "estudio_id": ids["e1"], "horario_inicio": "08:00",
            "horario_fim": "09:00", "tipo": "GRAVACAO_ANTECIPADA", "titulo": "Gravação antecipada 3ª série",
            "chamado": "#17690"}
    r = client.post(f"{URL}/agendamentos", json=base, headers=admin_headers)
    assert r.status_code == 409 and r.json()["detail"]["tipo"] == "confirmar"
    assert len(r.json()["detail"]["aulas"]) == 2

    r = client.post(f"{URL}/agendamentos", json={**base, "cancelar_aulas_conflitantes": True}, headers=admin_headers)
    assert r.status_code == 201 and r.json()["aulas_canceladas"] == 2 and r.json()["chamado"] == "17690"
    ag_id = r.json()["id"]

    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    itens = _coluna(agenda, "manha", ids["e1"])["itens"]
    assert [i["cancelada"] for i in itens if i["tipo"] == "AULA"] == [True, True]
    assert any(i["tipo"] == "GRAVACAO_ANTECIPADA" and not i["cancelada"] for i in itens)
    assert agenda["resumo"]["aulas_canceladas"] == 2 and agenda["resumo"]["agendamentos"] == 1

    # Outro agendamento no mesmo horário: bloqueado
    r = client.post(f"{URL}/agendamentos", json={**base, "horario_inicio": "08:30", "horario_fim": "08:45",
                                                 "cancelar_aulas_conflitantes": True}, headers=admin_headers)
    assert r.status_code == 409 and r.json()["detail"]["tipo"] == "agendamento"

    # Restaurar aula com o estúdio ocupado: bloqueado
    grade_id = next(i["grade_id"] for i in itens if i["tipo"] == "AULA")
    r = client.post(f"{URL}/aulas/restaurar", json={"data": QUARTA.isoformat(), "grade_id": grade_id},
                    headers=admin_headers)
    assert r.status_code == 409

    # Cancelando o agendamento o estúdio libera
    r = client.patch(f"{URL}/agendamentos/{ag_id}/status", json={"status": "CANCELADO"}, headers=admin_headers)
    assert r.json()["status"] == "CANCELADO"
    r = client.post(f"{URL}/aulas/restaurar", json={"data": QUARTA.isoformat(), "grade_id": grade_id},
                    headers=admin_headers)
    assert r.status_code == 200
    # Reativar agora bate com a aula restaurada
    r = client.patch(f"{URL}/agendamentos/{ag_id}/status", json={"status": "AGENDADO"}, headers=admin_headers)
    assert r.status_code == 409


def test_agendamento_em_horario_livre_e_listagem(client, db_session, admin_headers):
    ids = _cenario(db_session)
    r = client.post(f"{URL}/agendamentos", json={
        "data": QUARTA.isoformat(), "estudio_id": ids["e2"], "horario_inicio": "10:50", "horario_fim": "11:50",
        "tipo": "RESERVA", "titulo": "Reservado UAPI", "professor": "Fulano", "turma_id": ids["turma"],
    }, headers=admin_headers)
    assert r.status_code == 201
    ag = r.json()
    assert ag["turno"] == "manha" and ag["turma"] == "EM 1 TI"

    # Horário inválido e estúdio inativo
    ruim = {**ag, "horario_inicio": "11:00", "horario_fim": "10:00", "tipo": "RESERVA"}
    assert client.post(f"{URL}/agendamentos", json=ruim, headers=admin_headers).status_code == 422

    # Editar
    r = client.put(f"{URL}/agendamentos/{ag['id']}", json={
        "data": QUARTA.isoformat(), "estudio_id": ids["e2"], "horario_inicio": "10:50", "horario_fim": "12:00",
        "tipo": "RESERVA", "titulo": "Reservado UAPI - Sistemas para Internet",
    }, headers=admin_headers)
    assert r.status_code == 200 and r.json()["horario_fim"] == "12:00"

    lista = client.get(f"{URL}/agendamentos", params={"data_inicio": "2026-08-01", "data_fim": "2026-08-31",
                                                      "busca": "uapi"}, headers=admin_headers).json()
    assert lista["total"] == 1
    assert client.delete(f"{URL}/agendamentos/{ag['id']}", headers=admin_headers).status_code == 204
    lista = client.get(f"{URL}/agendamentos", params={"data_inicio": "2026-08-01", "data_fim": "2026-08-31"},
                       headers=admin_headers).json()
    assert lista["total"] == 0


def test_cancelar_aula_avulsa_e_exportar_planilha(client, db_session, admin_headers):
    ids = _cenario(db_session)
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    aula = _coluna(agenda, "tarde", ids["e1"])["itens"][0]
    r = client.post(f"{URL}/aulas/cancelar", json={"data": QUARTA.isoformat(), "grade_id": aula["grade_id"],
                                                   "motivo": "Professor ausente"}, headers=admin_headers)
    assert r.status_code == 201
    # Dia errado para esse slot
    r = client.post(f"{URL}/aulas/cancelar", json={"data": "2026-08-06", "grade_id": aula["grade_id"]},
                    headers=admin_headers)
    assert r.status_code == 404

    client.put(f"{URL}/escala-dia", json={"data": "2026-08-05", "turno": "manha", "estudio_id": ids["e1"],
                                          "diretor_imagem_id": ids["d1"]}, headers=admin_headers)
    r = client.get(f"{URL}/exportar", params={"data_inicio": "2026-08-05", "data_fim": "2026-08-06"},
                   headers=admin_headers)
    assert r.status_code == 200
    wb = load_workbook(BytesIO(r.content))
    assert wb.sheetnames == ["05-08", "06-08"]
    textos = [str(c.value) for row in wb["05-08"].iter_rows() for c in row if c.value]
    assert "MAYOLLY" in textos
    assert any("FÍSICA" in t and "Prof. Física" in t for t in textos)
    assert any("CANCELADO" in t for t in textos)
    r = client.get(f"{URL}/exportar", params={"data_inicio": "2026-01-01", "data_fim": "2026-06-01"},
                   headers=admin_headers)
    assert r.status_code == 422


# ─── Conferência com o que o sistema já tem ───────────────────────────

def _cr(db, turma_id, disc_id, **kw):
    base = dict(
        created_by=uuid.uuid4(), status="VALIDADO", data_aula=QUARTA, turno="Manhã", estudio="ESTÚDIO 1",
        turma_id=turma_id, disciplina_id=disc_id, horario_aula="07:30 às 08:30", tipo_aula="Transmissão ao vivo",
        canal_utilizado="1", conteudo_ministrado="X", status_compliance="Pendente",
    )
    base.update(kw)
    r = ClassReport(**base)
    db.add(r)
    db.commit()
    return r


def test_grade_igual_a_auditoria_versao_ativa_substitui_legado(client, db_session, admin_headers):
    """A agenda usa a mesma regra dos 'Previstos' da Auditoria: turma com versão ativa ignora o legado."""
    e1 = Estudio(nome="Estúdio 01", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    turma = Turma(nome="T", modalidade="REGULAR", serie_modulo="1", turno="MANHÃ", nomenclatura_padrao="EM 1 TIM")
    disc = Disciplina(nome="HISTÓRIA")
    db_session.add_all([e1, turma, disc])
    db_session.flush()
    # legado antigo (07:00) + versão ativa nova (07:30) para a mesma quarta
    db_session.add(Grade(turma_id=turma.id, disciplina_id=disc.id, estudio_id=e1.id, dia_semana=2,
                         horario_inicio=time(7, 0), horario_fim=time(8, 0)))
    v = GradeVersao(turma_id=turma.id, is_active=True)
    db_session.add(v)
    db_session.flush()
    db_session.add(Grade(turma_id=turma.id, grade_versao_id=v.id, disciplina_id=disc.id, estudio_id=e1.id,
                         dia_semana=2, horario_inicio=time(7, 30), horario_fim=time(8, 30)))
    db_session.commit()

    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    assert [i["inicio"] for i in _coluna(agenda, "manha", e1.id)["itens"]] == ["07:30"]
    auditoria = client.get("/api/v1/reports/audit-stats", params={"data_inicio": QUARTA.isoformat(),
                                                                  "data_fim": QUARTA.isoformat()},
                           headers=admin_headers).json()
    assert agenda["resumo"]["aulas"] == auditoria["total_grades"] == 1


def test_conferencia_aponta_o_que_nao_bate(client, db_session, admin_headers):
    ids = _cenario(db_session)
    e1, e2 = ids["e1"], ids["e2"]
    turma = db_session.query(Turma).filter(Turma.nomenclatura_padrao == "EM 1 TI").first()
    fis = db_session.query(Disciplina).filter(Disciplina.nome == "FÍSICA").first()
    mat = db_session.query(Disciplina).filter(Disciplina.nome == "MATEMÁTICA").first()
    outra = Turma(nome="2ª", modalidade="REGULAR", serie_modulo="2", turno="MANHÃ", nomenclatura_padrao="EM 2 TIM")
    db_session.add(outra)
    db_session.flush()
    db_session.add_all([
        # choque: outra turma no mesmo estúdio e horário
        Grade(turma_id=outra.id, disciplina_id=fis.id, estudio_id=e1, dia_semana=2,
              horario_inicio=time(7, 30), horario_fim=time(8, 30)),
        # duplicata exata
        Grade(turma_id=turma.id, disciplina_id=mat.id, estudio_id=e1, dia_semana=2,
              horario_inicio=time(12, 50), horario_fim=time(13, 50)),
        # sem estúdio
        Grade(turma_id=outra.id, disciplina_id=mat.id, estudio_id=None, dia_semana=2,
              horario_inicio=time(9, 50), horario_fim=time(10, 50)),
    ])
    db_session.commit()

    # Relatório de aula: física 07:30 validado (casa com a grade); matemática 08:30 em estúdio errado
    _cr(db_session, turma.id, fis.id, start_time=time(7, 30), end_time=time(8, 30))
    _cr(db_session, turma.id, mat.id, horario_aula="08:30 às 09:30", estudio="ESTÚDIO 2", status="RASCUNHO")
    # Relatório de aula que não está na agenda
    quim = Disciplina(nome="QUÍMICA")
    db_session.add(quim)
    db_session.commit()
    _cr(db_session, outra.id, quim.id, horario_aula="14:00 às 15:00", estudio="ESTÚDIO 2",
        start_time=time(14, 0), end_time=time(15, 0))
    # Diretor escalado MAYOLLY, mas quem fez o relatório de imagem foi FLAVILTON
    client.put(f"{URL}/escala-dia", json={"data": QUARTA.isoformat(), "turno": "manha", "estudio_id": e1,
                                          "diretor_imagem_id": ids["d1"]}, headers=admin_headers)
    chefe = db_session.query(User).first()
    db_session.add(ImageDirectorReport(created_by=chefe.id, diretor_imagem_id=uuid.UUID(ids["d2"]),
                                       data_relatorio=QUARTA, turno="MANHÃ", estudio="Estúdio 1"))
    db_session.commit()

    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    msgs = " | ".join(c["mensagem"] for c in agenda["conferencia"])
    niveis = {c["nivel"] for c in agenda["conferencia"]}
    assert "erro" in niveis and "dois usos no mesmo horário" in msgs
    assert "Aula repetida na grade" in msgs
    assert "sem estúdio definido" in msgs
    assert "Relatório de aula diz ESTÚDIO 2, a grade diz Estúdio 01" in msgs
    assert "Relatório de aula sem aula prevista" in msgs
    assert "relatório de imagem foi feito por FLAVILTON" in msgs

    manha = _coluna(agenda, "manha", e1)
    fisica = next(i for i in manha["itens"] if i["titulo"] == "FÍSICA" and i["turma"] == "EM 1 TI")
    assert fisica["relatorio"]["status"] == "VALIDADO"
    assert manha["diretor_relatorio"] == ["FLAVILTON"]
    # duplicata aparece uma vez só
    assert [i["inicio"] for i in _coluna(agenda, "tarde", e1)["itens"]] == ["12:50"]
    assert agenda["resumo"]["inconsistencias"] >= 5


def test_reserva_checa_o_que_ja_esta_cadastrado(client, db_session, admin_headers):
    ids = _cenario(db_session)
    e2 = ids["e2"]
    est = db_session.get(Estudio, e2)
    est.horario_inicio, est.horario_fim = time(7, 0), time(18, 0)
    db_session.commit()
    base = {"data": QUARTA.isoformat(), "estudio_id": e2, "horario_inicio": "07:45", "horario_fim": "08:15",
            "tipo": "GRAVACAO_ANTECIPADA", "titulo": "Gravação"}

    # Fora do funcionamento do estúdio: bloqueia
    r = client.post(f"{URL}/agendamentos", json={**base, "horario_inicio": "18:30", "horario_fim": "19:00"},
                    headers=admin_headers)
    assert r.status_code == 422 and "funciona" in r.json()["detail"]

    # Professor e turma já têm aula da grade nesse horário em outro estúdio: pede confirmação
    r = client.post(f"{URL}/agendamentos", json={**base, "professor": "prof. física", "turma_id": ids["turma"]},
                    headers=admin_headers)
    assert r.status_code == 409
    avisos = r.json()["detail"]["avisos"]
    assert any("professor Prof. Física" in a for a in avisos)
    assert any("turma EM 1 TI" in a for a in avisos)
    assert r.json()["detail"]["aulas"] == []

    # Relatório de aula já registrado nesse estúdio/horário
    turma = db_session.query(Turma).filter(Turma.nomenclatura_padrao == "EM 1 TI").first()
    fis = db_session.query(Disciplina).filter(Disciplina.nome == "FÍSICA").first()
    _cr(db_session, turma.id, fis.id, estudio="ESTÚDIO 02", start_time=time(8, 0), end_time=time(9, 0))
    r = client.post(f"{URL}/agendamentos", json=base, headers=admin_headers)
    assert r.status_code == 409 and any("relatório de aula registrado" in a for a in r.json()["detail"]["avisos"])

    # Ciente: grava
    r = client.post(f"{URL}/agendamentos", json={**base, "confirmar_avisos": True}, headers=admin_headers)
    assert r.status_code == 201

    # Mesmo professor em outro estúdio no mesmo horário (agendamento x agendamento)
    client.post(f"{URL}/agendamentos", json={**base, "horario_inicio": "15:00", "horario_fim": "16:00",
                                             "professor": "Fulano"}, headers=admin_headers)
    r = client.post(f"{URL}/agendamentos", json={**base, "estudio_id": ids["e1"], "horario_inicio": "15:30",
                                                 "horario_fim": "16:30", "professor": "FULANO"}, headers=admin_headers)
    assert r.status_code == 409 and any("já está agendado" in a for a in r.json()["detail"]["avisos"])


def test_cancelar_aula_que_nao_esta_prevista_no_dia(client, db_session, admin_headers):
    ids = _cenario(db_session)
    # slot de versão inativa (existe na tabela, mas não está previsto)
    inativo = db_session.query(Grade).join(GradeVersao, Grade.grade_versao_id == GradeVersao.id).first()
    r = client.post(f"{URL}/aulas/cancelar", json={"data": QUARTA.isoformat(), "grade_id": str(inativo.id)},
                    headers=admin_headers)
    assert r.status_code == 404


# ─── Reunião com os diretores-chefes ─────────────────────────────────

def test_regra_do_verde_disponivel():
    from app.services.agenda_estudios import horarios_livres
    m = lambda h: int(h[:2]) * 60 + int(h[3:])  # noqa: E731
    tarde = (m("12:50"), m("18:20"))
    # Estúdio cuja noite começa 18:00 (EJA): aula até 17:10 → 17:10–17:50 = 40 min, não serve
    aulas_tarde = [(m("12:50"), m("14:50")), (m("15:10"), m("17:10"))]
    assert horarios_livres(aulas_tarde + [(m("18:00"), m("19:00"))], tarde) == []
    # Estúdio 3 (Ensino Médio começa 18:30): pode agendar até 18:20
    assert horarios_livres(aulas_tarde + [(m("18:30"), m("19:15"))], tarde) == [(m("17:10"), m("18:20"))]
    # Horário trancado tira o espaço
    assert horarios_livres([(m("12:50"), m("16:10"))], tarde, bloqueados=[(m("16:10"), m("18:20"))]) == []


def test_disponivel_e_trancado_na_agenda(client, db_session, admin_headers):
    ids = _cenario(db_session)
    futuro = QUARTA + timedelta(days=7 * 60)  # uma quarta no futuro
    r = client.post(f"{URL}/bloqueios", json={"estudio_id": ids["e2"], "dias_semana": [2], "horario_inicio": "12:50",
                                              "horario_fim": "18:20", "motivo": "noite começa 18:00"},
                    headers=admin_headers)
    assert r.status_code == 201
    agenda = client.get(f"{URL}/dia", params={"data": futuro.isoformat()}, headers=admin_headers).json()
    tarde_e2 = _coluna(agenda, "tarde", ids["e2"])
    assert tarde_e2["bloqueios"][0]["motivo"] == "noite começa 18:00" and tarde_e2["livres"] == []
    manha_e1 = _coluna(agenda, "manha", ids["e1"])
    # E1 manhã: aulas 07:30–09:30 → livre 09:30–12:20
    assert manha_e1["livres"] == [{"inicio": "09:30", "fim": "12:20"}]
    # Agendar em horário trancado pede confirmação
    base = {"data": futuro.isoformat(), "estudio_id": ids["e2"], "horario_inicio": "14:00", "horario_fim": "15:00",
            "tipo": "EVENTO", "titulo": "Evento SUGED", "departamento": "SUGED"}
    r = client.post(f"{URL}/agendamentos", json=base, headers=admin_headers)
    assert r.status_code == 409 and any("trancado" in a for a in r.json()["detail"]["avisos"])
    r = client.post(f"{URL}/agendamentos", json={**base, "confirmar_avisos": True}, headers=admin_headers)
    assert r.status_code == 201 and r.json()["departamento"] == "SUGED"
    # Margem de segurança: terminar colado na próxima aula
    r = client.post(f"{URL}/agendamentos", json={**base, "estudio_id": ids["e1"], "horario_inicio": "11:55",
                                                 "horario_fim": "12:45", "tipo": "PODCAST", "titulo": "Podcast"},
                    headers=admin_headers)
    assert r.status_code == 409 and any("margem de segurança" in a for a in r.json()["detail"]["avisos"])
    # Passado não mostra disponível
    passado = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    assert _coluna(passado, "manha", ids["e1"])["livres"] == []


def test_remanejar_aula_no_dia_com_canal(client, db_session, admin_headers):
    from app.models.infraestrutura import CanalIptvModel
    ids = _cenario(db_session)
    canal = CanalIptvModel(nome="SEDUC-PI8", numero=8)
    db_session.add(canal)
    db_session.commit()
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    aula = _coluna(agenda, "manha", ids["e1"])["itens"][0]  # FÍSICA 07:30
    r = client.post(f"{URL}/aulas/remanejar", json={"data": QUARTA.isoformat(), "grade_id": aula["grade_id"],
                                                   "estudio_destino_id": ids["e2"], "canal_iptv_id": canal.id,
                                                   "motivo": "manutenção no Estúdio 01"}, headers=admin_headers)
    assert r.status_code == 201 and r.json()["tipo"] == "AULA_REMANEJADA" and r.json()["canal"] == "SEDUC-PI8"

    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    destino = _coluna(agenda, "manha", ids["e2"])["itens"]
    origem = _coluna(agenda, "manha", ids["e1"])["itens"]
    assert destino[0]["remanejada"] and destino[0]["remanejada_de"] == "Estúdio 01" and destino[0]["canal"] == "SEDUC-PI8"
    # No estúdio de origem a aula some (sem o bloco tracejado)
    assert [i["titulo"] for i in origem] == ["MATEMÁTICA"]
    assert agenda["resumo"]["aulas"] == 3 and agenda["resumo"]["aulas_remanejadas"] == 1

    # O estúdio de origem ficou livre nesse horário; o destino ficou ocupado
    livre = {"data": QUARTA.isoformat(), "horario_inicio": "07:30", "horario_fim": "08:30",
             "tipo": "MANUTENCAO", "titulo": "Manutenção", "estudio_id": ids["e1"], "confirmar_avisos": True}
    assert client.post(f"{URL}/agendamentos", json=livre, headers=admin_headers).status_code == 201
    r = client.post(f"{URL}/agendamentos", json={**livre, "estudio_id": ids["e2"], "titulo": "Outra"},
                    headers=admin_headers)
    assert r.status_code == 409 and len(r.json()["detail"]["aulas"]) == 1

    # Remanejar para um estúdio ocupado: bloqueia
    mat = _coluna(agenda, "manha", ids["e1"])["itens"][0]  # MATEMÁTICA 08:30 (a FÍSICA saiu daqui)
    r = client.post(f"{URL}/aulas/remanejar", json={"data": QUARTA.isoformat(), "grade_id": mat["grade_id"],
                                                   "estudio_destino_id": ids["e1"]}, headers=admin_headers)
    assert r.status_code == 422  # é o próprio estúdio da grade

    # Voltar para o estúdio da grade: bloqueado porque a manutenção ocupa o E1
    r = client.post(f"{URL}/aulas/restaurar", json={"data": QUARTA.isoformat(), "grade_id": aula["grade_id"]},
                    headers=admin_headers)
    assert r.status_code == 409

    # Excel mostra o remanejamento
    wb = load_workbook(BytesIO(client.get(f"{URL}/exportar", params={"data_inicio": QUARTA.isoformat()},
                                          headers=admin_headers).content))
    textos = " | ".join(str(c.value) for row in wb.active.iter_rows() for c in row if c.value)
    assert "remanejada do Estúdio 01" in textos and "SEDUC-PI8" in textos


def test_aula_sem_relatorio_nas_ultimas_semanas(client, db_session, admin_headers):
    ids = _cenario(db_session)
    turma = db_session.query(Turma).filter(Turma.nomenclatura_padrao == "EM 1 TI").first()
    fis = db_session.query(Disciplina).filter(Disciplina.nome == "FÍSICA").first()
    # Nas 3 quartas anteriores só a FÍSICA teve relatório; a MATEMÁTICA das 08:30 nunca
    for semanas in (1, 2, 3):
        _cr(db_session, turma.id, fis.id, data_aula=QUARTA - timedelta(days=7 * semanas),
            start_time=time(7, 30), end_time=time(8, 30))
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    msgs = [c["mensagem"] for c in agenda["conferencia"] if c["categoria"] == "grade_desatualizada"]
    assert any("MATEMÁTICA · 08:30" in m for m in msgs)
    assert not any("FÍSICA · 07:30" in m for m in msgs)


def test_colunas_novas_em_tabela_ja_existente():
    from sqlalchemy import create_engine, inspect, text
    from app.models.agenda_estudio import garantir_colunas_agenda
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE canal_iptv (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE agenda_agendamentos (id VARCHAR(36) PRIMARY KEY, titulo VARCHAR(255))"))
    garantir_colunas_agenda(eng)
    garantir_colunas_agenda(eng)  # idempotente
    cols = {c["name"] for c in inspect(eng).get_columns("agenda_agendamentos")}
    assert {"canal_iptv_id", "departamento"} <= cols


def test_feriado_tranca_o_dia(client, db_session, admin_headers):
    ids = _cenario(db_session)
    r = client.post(f"{URL}/feriados", json={"data": QUARTA.isoformat(), "nome": "Feriado municipal"},
                    headers=admin_headers)
    assert r.status_code == 201
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    assert agenda["feriado"]["nome"] == "Feriado municipal"
    assert _coluna(agenda, "manha", ids["e1"])["livres"] == []
    assert not any(c["categoria"] == "diretor" for c in agenda["conferencia"])
    r = client.post(f"{URL}/agendamentos", json={"data": QUARTA.isoformat(), "estudio_id": ids["e2"],
                                                 "horario_inicio": "10:00", "horario_fim": "11:00",
                                                 "tipo": "EVENTO", "titulo": "Evento"}, headers=admin_headers)
    assert r.status_code == 422 and "feriado" in r.json()["detail"].lower()
    lista = client.get(f"{URL}/feriados", headers=admin_headers).json()
    client.delete(f"{URL}/feriados/{lista[0]['id']}", headers=admin_headers)
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    assert not agenda.get("feriado")


def test_sob_demanda_fica_verde_com_minimo(client, db_session, admin_headers):
    ids = _cenario(db_session)
    futuro = QUARTA + timedelta(days=7 * 60)
    r = client.post(f"{URL}/bloqueios", json={"estudio_id": ids["e2"], "dias_semana": [2], "horario_inicio": "07:00",
                                              "horario_fim": "12:20", "tipo": "SOB_DEMANDA"}, headers=admin_headers)
    assert r.status_code == 201 and r.json()["minimo_aulas"] == 3
    agenda = client.get(f"{URL}/dia", params={"data": futuro.isoformat()}, headers=admin_headers).json()
    livres = _coluna(agenda, "manha", ids["e2"])["livres"]
    assert livres and livres[0]["sob_demanda"] and livres[0]["minimo_aulas"] == 3
    assert client.post(f"{URL}/bloqueios", json={"estudio_id": ids["e2"], "dias_semana": [2],
                                                 "horario_inicio": "07:00", "horario_fim": "08:00",
                                                 "tipo": "XPTO"}, headers=admin_headers).status_code == 422


def test_evento_remaneja_aulas_sem_deixar_aula_sem_estudio(client, db_session, admin_headers):
    ids = _cenario(db_session)
    base = {"data": QUARTA.isoformat(), "estudio_id": ids["e1"], "horario_inicio": "07:30",
            "horario_fim": "09:30", "tipo": "EVENTO", "titulo": "Live SEDUC", "departamento": "UETEV",
            "confirmar_avisos": True}
    r = client.post(f"{URL}/agendamentos", json=base, headers=admin_headers)
    assert r.status_code == 409
    detalhe = r.json()["detail"]["aulas_detalhe"]
    assert len(detalhe) == 2
    # O Estúdio 02 está livre e aparece como sugestão para cada aula
    assert detalhe[0]["sugestoes"][0]["id"] == ids["e2"]
    # Destino ocupado pelo próprio evento: recusado
    r = client.post(f"{URL}/agendamentos", json={**base, "remanejar_aulas": [
        {"grade_id": d["grade_id"], "estudio_id": ids["e1"]} for d in detalhe]}, headers=admin_headers)
    assert r.status_code == 409 and r.json()["detail"]["tipo"] == "remanejo"
    # Física vai para o Estúdio 02; Matemática é cancelada no dia
    r = client.post(f"{URL}/agendamentos", json={**base, "remanejar_aulas": [
        {"grade_id": detalhe[0]["grade_id"], "estudio_id": ids["e2"]},
        {"grade_id": detalhe[1]["grade_id"], "estudio_id": None}]}, headers=admin_headers)
    assert r.status_code == 201
    assert r.json()["aulas_remanejadas"] == 1 and r.json()["aulas_canceladas"] == 1
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    destino = _coluna(agenda, "manha", ids["e2"])["itens"]
    assert any(i.get("remanejada") and i["titulo"] == "FÍSICA" for i in destino)
    # Remanejamento vale só para o dia: na quarta seguinte a aula está no Estúdio 01
    prox = client.get(f"{URL}/dia", params={"data": (QUARTA + timedelta(days=7)).isoformat()},
                      headers=admin_headers).json()
    assert [i["titulo"] for i in _coluna(prox, "manha", ids["e1"])["itens"]] == ["FÍSICA", "MATEMÁTICA"]


def test_sugestoes_priorizam_evento_e_libras(client, db_session, admin_headers):
    ids = _cenario(db_session)
    e3 = Estudio(nome="Estúdio 03", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    db_session.add(e3)
    db_session.commit()
    assert client.put(f"{URL}/estudios-config/{e3.id}", json={"libras": True, "prioridade_evento": 1},
                      headers=admin_headers).status_code == 200
    params = {"data": QUARTA.isoformat(), "inicio": "07:30", "fim": "08:30"}
    ev = client.get(f"{URL}/sugestoes", params={**params, "para": "evento"}, headers=admin_headers).json()
    assert ev[0]["id"] == e3.id and ev[0]["livre"]
    # E1 tem aula nesse horário: aparece depois dos livres, como ocupado
    assert ev[-1]["id"] == ids["e1"] and not ev[-1]["livre"]
    cfg = client.get(f"{URL}/estudios-config", headers=admin_headers).json()
    assert next(c for c in cfg if c["estudio_id"] == e3.id)["libras"] is True


def test_observacoes_no_bloco(client, db_session, admin_headers):
    ids = _cenario(db_session)
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    aula = _coluna(agenda, "manha", ids["e1"])["itens"][0]
    for texto in ("Professor atrasou 10 min", "Problema de áudio"):
        r = client.post(f"{URL}/observacoes", json={"data": QUARTA.isoformat(), "grade_id": aula["grade_id"],
                                                    "texto": texto, "link": "https://tomticket.com/1"},
                        headers=admin_headers)
        assert r.status_code == 201
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    obs = _coluna(agenda, "manha", ids["e1"])["itens"][0]["observacoes"]
    assert [o["texto"] for o in obs] == ["Professor atrasou 10 min", "Problema de áudio"]
    assert client.delete(f"{URL}/observacoes/{obs[0]['id']}", headers=admin_headers).status_code == 204
    # Na outra quarta a observação não aparece
    prox = client.get(f"{URL}/dia", params={"data": (QUARTA + timedelta(days=7)).isoformat()},
                      headers=admin_headers).json()
    assert _coluna(prox, "manha", ids["e1"])["itens"][0]["observacoes"] == []
    assert client.post(f"{URL}/observacoes", json={"data": QUARTA.isoformat(), "texto": "x"},
                       headers=admin_headers).status_code == 422


def test_dois_diretores_no_turno(client, db_session, admin_headers):
    ids = _cenario(db_session)
    r = client.put(f"{URL}/escala-dia", json={"data": QUARTA.isoformat(), "turno": "manha", "estudio_id": ids["e1"],
                                              "diretor_imagem_id": ids["d1"], "diretor2_imagem_id": ids["d2"],
                                              "troca_horario": "09:30"}, headers=admin_headers)
    assert r.status_code == 200
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    d = _coluna(agenda, "manha", ids["e1"])["diretor"]
    assert d["nome"] == "MAYOLLY" and d["nome2"] == "FLAVILTON" and d["troca_horario"] == "09:30"
    r = client.put(f"{URL}/escala-dia", json={"data": QUARTA.isoformat(), "turno": "manha", "estudio_id": ids["e1"],
                                              "diretor_imagem_id": ids["d1"], "diretor2_imagem_id": ids["d1"]},
                   headers=admin_headers)
    assert r.status_code == 422


def test_estudio_fixo_e_estudio_da_aula_para_o_relatorio(client, db_session, admin_headers, assistant_headers):
    ids = _cenario(db_session)
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    fis, mat = _coluna(agenda, "manha", ids["e1"])["itens"][:2]
    q = {"turma_id": ids["turma"], "data": QUARTA.isoformat(), "horario": "1º Horário", "turno": "INTEGRAL"}
    # O assistente consulta o estúdio pelo nº do horário (o mesmo texto do cadastro de estúdios)
    r = client.get(f"{URL}/estudio-da-aula", params=q, headers=assistant_headers).json()
    assert r["encontrado"] and r["estudio"] == "Estúdio 01" and r["disciplina"] == "FÍSICA"
    r = client.get(f"{URL}/estudio-da-aula", params={**q, "horario": None, "inicio": "08:30"},
                   headers=assistant_headers).json()
    assert r["estudio"] == "Estúdio 01" and r["disciplina"] == "MATEMÁTICA"
    # Remanejada no dia: o relatório já sai com o estúdio de destino
    client.post(f"{URL}/aulas/remanejar", json={"data": QUARTA.isoformat(), "grade_id": fis["grade_id"],
                                                "estudio_destino_id": ids["e2"]}, headers=admin_headers)
    r = client.get(f"{URL}/estudio-da-aula", params=q, headers=assistant_headers).json()
    assert r["estudio"] == "Estúdio 02" and r["remanejada"] and r["estudio_grade"] == "Estúdio 01"
    # Sem aula nesse horário: o assistente escolhe
    r = client.get(f"{URL}/estudio-da-aula", params={**q, "horario": "7º Horário"}, headers=assistant_headers).json()
    assert r["encontrado"] is False
    # Estúdio fixo: muda a grade (toda semana) — bloqueia se outro já usa
    assert client.put(f"{URL}/aulas/estudio-fixo", json={"grade_id": mat["grade_id"], "estudio_id": ids["e2"]},
                      headers=assistant_headers).status_code == 403
    r = client.put(f"{URL}/aulas/estudio-fixo", json={"grade_id": mat["grade_id"], "estudio_id": ids["e2"]},
                   headers=admin_headers)
    assert r.status_code == 200
    prox = (QUARTA + timedelta(days=7)).isoformat()
    r = client.get(f"{URL}/estudio-da-aula", params={**q, "data": prox, "horario": "2º Horário"},
                   headers=assistant_headers).json()
    assert r["estudio"] == "Estúdio 02"


def test_tres_diretores_no_turno(client, db_session, admin_headers):
    """Evento que atravessa o turno: o chefe adiciona quantos diretores precisar, cada um a partir de um horário."""
    from app.services.agenda_estudios import diretor_escalado, minha_escala
    ids = _cenario(db_session)
    d3 = DiretorImagem(nome="DORNELAS")
    db_session.add(d3)
    db_session.commit()
    base = {"data": QUARTA.isoformat(), "turno": "manha", "estudio_id": ids["e1"], "diretor_imagem_id": ids["d1"]}
    r = client.put(f"{URL}/escala-dia", json={**base, "trocas": [
        {"diretor_imagem_id": ids["d2"], "a_partir": "08:30"},
        {"diretor_imagem_id": str(d3.id), "a_partir": "10:00"}]}, headers=admin_headers)
    assert r.status_code == 200, r.text
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    d = _coluna(agenda, "manha", ids["e1"])["diretor"]
    assert [(t["nome"], t["a_partir"]) for t in d["trocas"]] == [("FLAVILTON", "08:30"), ("DORNELAS", "10:00")]
    # compatibilidade: o 2º diretor continua nos campos antigos
    assert d["nome2"] == "FLAVILTON" and d["troca_horario"] == "08:30"
    # quem responde pela aula depende do horário
    assert diretor_escalado(db_session, QUARTA, time(7, 30), ids["e1"])["diretor_nome"] == "MAYOLLY"
    assert diretor_escalado(db_session, QUARTA, time(8, 30), ids["e1"])["diretor_nome"] == "FLAVILTON"
    assert diretor_escalado(db_session, QUARTA, time(10, 30), ids["e1"])["diretor_nome"] == "DORNELAS"
    # o 3º diretor vê o estúdio na Minha Grade
    assert minha_escala(db_session, QUARTA, d3.id)["turnos"]
    lista = client.get(f"{URL}/escala-dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    assert len(lista[0]["trocas"]) == 2
    # copiar o dia leva todos os diretores
    prox = QUARTA + timedelta(days=7)
    client.post(f"{URL}/escala-dia/copiar", json={"de_data": QUARTA.isoformat(), "para_datas": [prox.isoformat()]},
                headers=admin_headers)
    lista = client.get(f"{URL}/escala-dia", params={"data": prox.isoformat()}, headers=admin_headers).json()
    assert len(lista[0]["trocas"]) == 2
    # validações: horário crescente, horário obrigatório com mais de uma troca, repetir o anterior
    for trocas in ([{"diretor_imagem_id": ids["d2"], "a_partir": "10:00"}, {"diretor_imagem_id": str(d3.id), "a_partir": "09:00"}],
                   [{"diretor_imagem_id": ids["d2"], "a_partir": "10:00"}, {"diretor_imagem_id": str(d3.id)}],
                   [{"diretor_imagem_id": ids["d1"], "a_partir": "10:00"}]):
        assert client.put(f"{URL}/escala-dia", json={**base, "trocas": trocas}, headers=admin_headers).status_code == 422
    # lista vazia remove as trocas
    client.put(f"{URL}/escala-dia", json={**base, "trocas": []}, headers=admin_headers)
    agenda = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    d = _coluna(agenda, "manha", ids["e1"])["diretor"]
    assert d["trocas"] == [] and d["nome2"] is None
