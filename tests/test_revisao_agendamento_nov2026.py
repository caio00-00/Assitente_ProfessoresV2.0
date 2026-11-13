"""Revisão da lógica de agendamento (13/11/2026): falhas e inconsistências corrigidas."""
from datetime import timedelta

from app.models.agenda_estudio import AgendamentoEstudio
from tests.test_agenda_estudios import QUARTA, URL, _cenario, _coluna


def _gravacao(ids, **extra):
    return {"data": QUARTA.isoformat(), "estudio_id": ids["e1"], "horario_inicio": "07:30", "horario_fim": "08:30",
            "tipo": "GRAVACAO", "titulo": "Gravação SEDUC", "confirmar_avisos": True, **extra}


def _ocupa_e1_cedo(client, admin_headers, ids, destino=None):
    """Agendamento no Estúdio 01 às 07:30, em cima da Física da grade (cancelada ou levada para o E2)."""
    dia = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    fisica = next(i for i in _coluna(dia, "manha", ids["e1"])["itens"] if i["titulo"] == "FÍSICA")
    r = client.post(f"{URL}/agendamentos", json=_gravacao(
        ids, remanejar_aulas=[{"grade_id": fisica["grade_id"], "estudio_id": destino}]), headers=admin_headers)
    assert r.status_code == 201, r.text
    return r.json(), fisica["grade_id"]


def _fisica(client, admin_headers, ids):
    dia = client.get(f"{URL}/dia", params={"data": QUARTA.isoformat()}, headers=admin_headers).json()
    for c in (_coluna(dia, "manha", ids["e1"]), _coluna(dia, "manha", ids["e2"])):
        for i in c["itens"]:
            if i["titulo"] == "FÍSICA" and i["tipo"] == "AULA":
                return c["estudio_id"], i
    raise AssertionError("Física sumiu da agenda")


def test_excluir_agendamento_devolve_a_aula_que_ele_tinha_cancelado(client, db_session, admin_headers):
    ids = _cenario(db_session)
    ag, _ = _ocupa_e1_cedo(client, admin_headers, ids)
    est, aula = _fisica(client, admin_headers, ids)
    assert aula["cancelada"] is True
    r = client.delete(f"{URL}/agendamentos/{ag['id']}", headers=admin_headers)
    assert r.status_code == 200 and r.json()["aulas_devolvidas"] == 1
    est, aula = _fisica(client, admin_headers, ids)
    assert est == ids["e1"] and aula["cancelada"] is False and aula["remanejada"] is False


def test_cancelar_agendamento_devolve_a_aula_remanejada_e_reativar_pede_de_novo(client, db_session, admin_headers):
    ids = _cenario(db_session)
    ag, _ = _ocupa_e1_cedo(client, admin_headers, ids, destino=ids["e2"])
    est, aula = _fisica(client, admin_headers, ids)
    assert est == ids["e2"] and aula["remanejada"] is True
    r = client.patch(f"{URL}/agendamentos/{ag['id']}/status", json={"status": "CANCELADO"}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["aulas_devolvidas"] == 1
    est, aula = _fisica(client, admin_headers, ids)
    assert est == ids["e1"] and aula["remanejada"] is False
    # Reativar: a aula voltou para o estúdio, então o horário está ocupado de novo
    r = client.patch(f"{URL}/agendamentos/{ag['id']}/status", json={"status": "AGENDADO"}, headers=admin_headers)
    assert r.status_code == 409


def test_mover_agendamento_devolve_so_a_aula_que_saiu_do_horario(client, db_session, admin_headers):
    ids = _cenario(db_session)
    ag, _ = _ocupa_e1_cedo(client, admin_headers, ids)
    corpo = {**_gravacao(ids), "titulo": "Gravação SEDUC (editada)"}
    # Só muda o título: a aula continua cancelada (a decisão já foi tomada)
    r = client.put(f"{URL}/agendamentos/{ag['id']}", json=corpo, headers=admin_headers)
    assert r.status_code == 200 and r.json()["aulas_devolvidas"] == 0
    assert _fisica(client, admin_headers, ids)[1]["cancelada"] is True
    # Arrasta para o Estúdio 02 (livre): a Física volta para o Estúdio 01
    r = client.put(f"{URL}/agendamentos/{ag['id']}", json={**corpo, "estudio_id": ids["e2"]}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["aulas_devolvidas"] == 1
    est, aula = _fisica(client, admin_headers, ids)
    assert est == ids["e1"] and aula["cancelada"] is False
    # Outro dia: também devolve (nada ficou preso na quarta)
    ag2, _ = _ocupa_e1_cedo(client, admin_headers, ids)
    outra = (QUARTA + timedelta(days=1)).isoformat()
    r = client.put(f"{URL}/agendamentos/{ag2['id']}", json={**_gravacao(ids), "data": outra, "estudio_id": ids["e2"]},
                   headers=admin_headers)
    assert r.status_code == 200 and r.json()["aulas_devolvidas"] == 1
    assert _fisica(client, admin_headers, ids)[1]["cancelada"] is False


def test_validacao_que_falha_nao_devolve_nada(client, db_session, admin_headers):
    """Se a edição é recusada (409/422), nada muda: a aula continua como estava."""
    ids = _cenario(db_session)
    ag, _ = _ocupa_e1_cedo(client, admin_headers, ids)
    r = client.put(f"{URL}/agendamentos/{ag['id']}", json={**_gravacao(ids), "estudio_id": ids["e2"],
                                                            "horario_fim": "07:00"}, headers=admin_headers)
    assert r.status_code == 422
    assert _fisica(client, admin_headers, ids)[1]["cancelada"] is True


def test_ocorrencia_de_aula_nao_se_apaga_pelo_excluir(client, db_session, admin_headers):
    ids = _cenario(db_session)
    _, grade_id = _ocupa_e1_cedo(client, admin_headers, ids)
    o = db_session.query(AgendamentoEstudio).filter(AgendamentoEstudio.tipo == "AULA_CANCELADA").first()
    r = client.delete(f"{URL}/agendamentos/{o.id}", headers=admin_headers)
    assert r.status_code == 422 and "Restaurar" in r.json()["detail"]


def test_cancelar_agendamento_em_dia_que_virou_feriado(client, db_session, admin_headers):
    ids = _cenario(db_session)
    ag = client.post(f"{URL}/agendamentos", json={**_gravacao(ids), "horario_inicio": "10:00",
                                                  "horario_fim": "11:00"}, headers=admin_headers).json()
    assert client.post(f"{URL}/feriados", json={"data": QUARTA.isoformat(), "nome": "Ponto facultativo"},
                       headers=admin_headers).status_code in (200, 201)
    r = client.patch(f"{URL}/agendamentos/{ag['id']}/status", json={"status": "CANCELADO"}, headers=admin_headers)
    assert r.status_code == 200
    # reativar num feriado continua bloqueado
    r = client.patch(f"{URL}/agendamentos/{ag['id']}/status", json={"status": "AGENDADO"}, headers=admin_headers)
    assert r.status_code == 422


def test_duas_gravacoes_nao_podem_ir_ao_ar_na_mesma_aula(client, db_session, admin_headers):
    ids = _cenario(db_session)
    antes = QUARTA - timedelta(days=7)
    dia = client.get(f"{URL}/aulas-da-turma", params={"turma_id": ids["turma"], "data": QUARTA.isoformat()},
                     headers=admin_headers).json()
    aula = dia[0]["grade_id"]
    corpo = {**_gravacao(ids), "data": antes.isoformat(), "horario_inicio": "10:00", "horario_fim": "11:00",
             "turma_id": ids["turma"], "data_referencia": QUARTA.isoformat(), "grade_exibicao_id": aula}
    assert client.post(f"{URL}/agendamentos", json=corpo, headers=admin_headers).status_code == 201
    r = client.post(f"{URL}/agendamentos", json={**corpo, "horario_inicio": "14:00", "horario_fim": "15:00"},
                    headers=admin_headers)
    assert r.status_code == 409 and "já está ligada" in r.json()["detail"]


def test_editar_agendamento_cancelado_continua_validando_os_campos(client, db_session, admin_headers):
    ids = _cenario(db_session)
    ag = client.post(f"{URL}/agendamentos", json={**_gravacao(ids), "horario_inicio": "10:00",
                                                  "horario_fim": "11:00"}, headers=admin_headers).json()
    client.patch(f"{URL}/agendamentos/{ag['id']}/status", json={"status": "CANCELADO"}, headers=admin_headers)
    r = client.put(f"{URL}/agendamentos/{ag['id']}", json={
        **_gravacao(ids), "horario_inicio": "10:00", "horario_fim": "11:00",
        "turma_id": "00000000-0000-0000-0000-000000000000"}, headers=admin_headers)
    assert r.status_code == 422 and "Turma" in r.json()["detail"]


def test_aviso_turma_ocupada_por_outro_agendamento_e_margem_antes_de_agendamento(client, db_session, admin_headers):
    ids = _cenario(db_session)
    base = {"data": QUARTA.isoformat(), "estudio_id": ids["e2"], "horario_inicio": "14:00", "horario_fim": "15:00",
            "tipo": "AULA_EXTRA", "titulo": "Aula extra", "turma_id": ids["turma"]}
    assert client.post(f"{URL}/agendamentos", json=base, headers=admin_headers).status_code == 201
    # A mesma turma, mesmo horário, outro estúdio: aviso
    r = client.post(f"{URL}/agendamentos", json={**base, "estudio_id": ids["e1"]}, headers=admin_headers)
    assert r.status_code == 409 and any("turma" in a and "já está agendada" in a for a in r.json()["detail"]["avisos"])
    # Terminar 5 min antes de outro agendamento do mesmo estúdio: aviso de margem
    r = client.post(f"{URL}/agendamentos", json={**base, "turma_id": None, "horario_inicio": "13:00",
                                                 "horario_fim": "13:55", "titulo": "Reunião", "tipo": "RESERVA"},
                    headers=admin_headers)
    assert r.status_code == 409 and any("margem" in a for a in r.json()["detail"]["avisos"])
