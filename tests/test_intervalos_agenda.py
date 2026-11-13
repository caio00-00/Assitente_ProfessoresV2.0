"""
Intervalos da Agenda (06/11/2026):
- fixos: manhã 09:30–09:50 e tarde 14:50–15:10; Estúdio 4: 10:00–10:20 e 16:00–16:20;
- aparecem na coluna do estúdio e não contam como horário disponível;
- o diretor-chefe muda do dia escolhido em diante (ou só naquele dia);
- os dias que já passaram ficam com o intervalo que tinham.
"""
from datetime import date, time, timedelta

from app.models.agenda_estudio import IntervaloAgenda, semear_intervalos
from app.models.infraestrutura import Estudio
from app.services import agenda_estudios as svc

AG = "/api/v1/agenda-estudios"
HOJE = date.today()


def _estudios(db):
    e1 = Estudio(nome="ESTÚDIO 1", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    e4 = Estudio(nome="Estúdio 04", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    db.add_all([e1, e4])
    db.commit()
    return e1, e4


def _semear(db, desde):
    return semear_intervalos(db.get_bind(), hoje=desde)


def _vale(db, dia, est):
    return svc.intervalos_do_dia(db, dia, [est.id])


def test_valores_fixos_e_excecao_do_estudio_4(db_session):
    e1, e4 = _estudios(db_session)
    assert _semear(db_session, HOJE) == 4
    assert _semear(db_session, HOJE) == 0  # só uma vez
    v1, v4 = _vale(db_session, HOJE, e1), _vale(db_session, HOJE, e4)
    assert (v1[("manha", e1.id)]["inicio"], v1[("manha", e1.id)]["fim"]) == ("09:30", "09:50")
    assert (v1[("tarde", e1.id)]["inicio"], v1[("tarde", e1.id)]["fim"]) == ("14:50", "15:10")
    assert (v4[("manha", e4.id)]["inicio"], v4[("manha", e4.id)]["fim"]) == ("10:00", "10:20")
    assert (v4[("tarde", e4.id)]["inicio"], v4[("tarde", e4.id)]["fim"]) == ("16:00", "16:20")
    assert v4[("manha", e4.id)]["origem"] == "estudio"


def test_dia_que_ja_passou_nao_muda(db_session):
    e1, _ = _estudios(db_session)
    _semear(db_session, HOJE)
    assert _vale(db_session, HOJE - timedelta(days=1), e1) == {}  # antes de existir: sem intervalo


def test_mudanca_vale_do_dia_em_diante_e_guarda_o_antigo(client, db_session, admin_headers):
    e1, e4 = _estudios(db_session)
    _semear(db_session, HOJE - timedelta(days=10))
    amanha = HOJE + timedelta(days=1)
    r = client.post(f"{AG}/intervalos", headers=admin_headers, json={
        "turno": "manha", "horario_inicio": "09:40", "horario_fim": "10:00", "a_partir_de": amanha.isoformat()})
    assert r.status_code == 201, r.text
    assert _vale(db_session, HOJE, e1)[("manha", e1.id)]["inicio"] == "09:30"            # hoje: o antigo
    assert _vale(db_session, amanha, e1)[("manha", e1.id)]["inicio"] == "09:40"          # daí em diante: o novo
    assert _vale(db_session, amanha + timedelta(days=30), e1)[("manha", e1.id)]["inicio"] == "09:40"
    assert _vale(db_session, amanha, e4)[("manha", e4.id)]["inicio"] == "10:00"          # Estúdio 4 mantém o seu


def test_nao_aceita_mudar_dia_que_passou(client, db_session, admin_headers):
    _estudios(db_session)
    _semear(db_session, HOJE - timedelta(days=10))
    r = client.post(f"{AG}/intervalos", headers=admin_headers, json={
        "turno": "tarde", "horario_inicio": "15:00", "horario_fim": "15:20",
        "a_partir_de": (HOJE - timedelta(days=1)).isoformat()})
    assert r.status_code == 422
    antigo = db_session.query(IntervaloAgenda).filter(IntervaloAgenda.vigente_desde < HOJE).first()
    r = client.delete(f"{AG}/intervalos/{antigo.id}", headers=admin_headers)
    assert r.status_code == 422


def test_so_neste_dia_e_voltar_ao_padrao(client, db_session, admin_headers):
    e1, e4 = _estudios(db_session)
    _semear(db_session, HOJE)
    dia = HOJE + timedelta(days=2)
    r = client.post(f"{AG}/intervalos", headers=admin_headers, json={
        "turno": "tarde", "estudio_id": e1.id, "horario_inicio": "15:30", "horario_fim": "15:50",
        "a_partir_de": dia.isoformat(), "so_neste_dia": True})
    assert r.status_code == 201, r.text
    assert _vale(db_session, dia, e1)[("tarde", e1.id)]["inicio"] == "15:30"
    assert _vale(db_session, dia + timedelta(days=1), e1)[("tarde", e1.id)]["inicio"] == "14:50"
    # Estúdio 4 passa a seguir o padrão
    r = client.post(f"{AG}/intervalos", headers=admin_headers, json={
        "turno": "manha", "estudio_id": e4.id, "a_partir_de": dia.isoformat()})
    assert r.status_code == 201, r.text
    assert _vale(db_session, dia, e4)[("manha", e4.id)]["inicio"] == "09:30"
    assert _vale(db_session, HOJE, e4)[("manha", e4.id)]["inicio"] == "10:00"


def test_horario_fora_do_turno_e_quem_pode_mudar(client, db_session, admin_headers, assistant_headers):
    _estudios(db_session)
    r = client.post(f"{AG}/intervalos", headers=admin_headers, json={
        "turno": "manha", "horario_inicio": "14:50", "horario_fim": "15:10", "a_partir_de": HOJE.isoformat()})
    assert r.status_code == 422
    r = client.post(f"{AG}/intervalos", headers=assistant_headers, json={
        "turno": "manha", "horario_inicio": "09:30", "horario_fim": "09:50", "a_partir_de": HOJE.isoformat()})
    assert r.status_code == 403


def test_intervalo_na_agenda_do_dia_e_fora_do_disponivel(client, db_session, admin_headers):
    e1, e4 = _estudios(db_session)
    _semear(db_session, HOJE)
    dia = HOJE + timedelta(days=1)
    r = client.get(f"{AG}/dia", params={"data": dia.isoformat()}, headers=admin_headers)
    assert r.status_code == 200, r.text
    manha = next(t for t in r.json()["turnos"] if t["turno"] == "manha")
    col1 = next(c for c in manha["estudios"] if c["estudio_id"] == e1.id)
    col4 = next(c for c in manha["estudios"] if c["estudio_id"] == e4.id)
    assert (col1["intervalo"]["inicio"], col4["intervalo"]["inicio"]) == ("09:30", "10:00")
    for l in col1["livres"]:
        assert not (l["inicio"] < "09:50" and "09:30" < l["fim"])
    avisos = svc.avisos_agendamento(db_session, dia, e1.id, time(9, 0), time(10, 0), None, None)
    assert any("intervalo" in a for a in avisos)


def test_quadro_e_historico(client, db_session, admin_headers):
    _estudios(db_session)
    _semear(db_session, HOJE)
    r = client.get(f"{AG}/intervalos", headers=admin_headers).json()
    assert [t["turno"] for t in r["turnos"]] == ["manha", "tarde"]
    assert r["turnos"][0]["padrao"]["inicio"] == "09:30"
    assert len(r["historico"]) == 4
