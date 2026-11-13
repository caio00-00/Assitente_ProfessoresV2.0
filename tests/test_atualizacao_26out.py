"""
Reunião de 26/10/2026 — atualização SEDUC, gravações e faturamento por hora de estúdio:
- Agenda: tipo único "Gravação" (antigos convertidos), caixa SEDUC em todo agendamento,
  Reposição na gravação com a data da aula que não aconteceu;
- relatório do assistente: reposição vem da Agenda; exibição de aula gravada antes sai sem professor;
- coordenação: fila "prontos para validar" × "aguardando links" com o motivo;
- planilha única "Uso de Estúdio" (uma linha por hora; última com o tempo real) e API com os minutos exatos;
- exportação só para admin, gestor, coordenação e diretor-chefe;
- painel do professor: total de aulas (slots) e total de horas (tempo real);
- gravação da grade (MP): muda de horário no dia; aula da grade não.
"""
import io
import os
from datetime import date, time

import pytest
from openpyxl import load_workbook

from app.models.agenda_estudio import AgendamentoEstudio
from app.models.auxiliares import Disciplina, Grade, Professor
from app.models.class_report import ClassReport
from app.models.infraestrutura import Estudio
from app.models.turma import Turma

AG = "/api/v1/agenda-estudios"
QUA = date(2026, 10, 28)      # aula de quarta na grade
GRAV = date(2026, 11, 3)      # reposição gravada depois (terça)
CHAVE = "chave-teste-uso-estudio"


@pytest.fixture(autouse=True)
def _chave_externa(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("EXTERNAL_API_KEY", CHAVE)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _cenario(db, tipo_slot="aula"):
    e1 = Estudio(nome="ESTÚDIO 1", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    e2 = Estudio(nome="ESTÚDIO 2", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    t = Turma(nome="EM 2 MANHÃ", modalidade="REGULAR", serie_modulo="2", turno="MANHÃ", nomenclatura_padrao="EM 2 MANHÃ")
    d = Disciplina(nome="QUÍMICA")
    p = Professor(nome="BIA SOUZA")
    db.add_all([e1, e2, t, d, p])
    db.flush()
    g = Grade(turma_id=t.id, disciplina_id=d.id, estudio_id=e1.id, dia_semana=2, professor_id=p.id,
              horario_inicio=time(8, 30), horario_fim=time(9, 30), tipo_slot=tipo_slot)
    db.add(g)
    db.commit()
    return dict(e1=e1, e2=e2, t=t, d=d, p=p, g=g)


def _gravacao(s, **extra):
    corpo = {"data": GRAV.isoformat(), "estudio_id": s["e2"].id, "horario_inicio": "14:00", "horario_fim": "15:00",
             "tipo": "GRAVACAO", "titulo": "Química", "turma_id": str(s["t"].id), "confirmar_avisos": True}
    corpo.update(extra)
    return corpo


def _cr(db, s, user_id, **kw):
    base = dict(created_by=user_id, status="AGUARDANDO_VALIDACAO", data_aula=QUA, turno="Manhã",
                estudio="ESTÚDIO 1", turma_id=s["t"].id, disciplina_id=s["d"].id, professor_id=s["p"].id,
                horario_aula="08:30 às 09:30", start_time=time(8, 30), end_time=time(9, 30),
                tipo_aula="Transmissão ao vivo", canal_utilizado="N/A", conteudo_ministrado="Reações",
                status_compliance="Pendente", nome_ficheiro_gerado="EM 2 QUIMICA X.mp4")
    base.update(kw)
    r = ClassReport(**base)
    db.add(r)
    db.commit()
    return r


# ─── Agenda ────────────────────────────────────────────────────────────

def test_tipo_gravacao_e_o_padrao_e_os_antigos_ficam_ocultos(client, admin_headers):
    tipos = client.get(f"{AG}/opcoes", headers=admin_headers).json()["tipos"]
    visiveis = [t["valor"] for t in tipos if not t.get("oculto")]
    assert visiveis[0] == "GRAVACAO"
    for antigo in ("GRAVACAO_ANTECIPADA", "REPOSICAO", "CURSO_TECNICO", "REGRAVACAO", "ASSINCRONA"):
        assert antigo not in visiveis


def test_caixa_seduc_em_qualquer_tipo_exige_chamado(client, db_session, admin_headers):
    s = _cenario(db_session)
    pod = {"data": GRAV.isoformat(), "estudio_id": s["e1"].id, "horario_inicio": "16:00", "horario_fim": "17:00",
           "tipo": "PODCAST", "titulo": "Podcast", "solicitante_antecipacao": "SEDUC", "confirmar_avisos": True}
    r = client.post(f"{AG}/agendamentos", json=pod, headers=admin_headers)
    assert r.status_code == 422 and "chamado" in r.json()["detail"].lower()
    r = client.post(f"{AG}/agendamentos", json={**pod, "chamado": "555"}, headers=admin_headers)
    assert r.status_code == 201, r.text
    assert r.json()["solicitante_antecipacao"] == "SEDUC" and r.json()["reposicao"] is False


def test_reposicao_precisa_da_data_da_aula_que_nao_aconteceu(client, db_session, admin_headers):
    s = _cenario(db_session)
    r = client.post(f"{AG}/agendamentos", json=_gravacao(s, reposicao=True), headers=admin_headers)
    assert r.status_code == 422 and "reposição" in r.json()["detail"].lower()
    # a aula que não aconteceu precisa ser ANTES da gravação
    r = client.post(f"{AG}/agendamentos", json=_gravacao(s, reposicao=True, data_referencia="2026-11-10"),
                    headers=admin_headers)
    assert r.status_code == 422
    r = client.post(f"{AG}/agendamentos", json=_gravacao(s, reposicao=True, data_referencia=QUA.isoformat(),
                                                         grade_exibicao_id=str(s["g"].id)), headers=admin_headers)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["reposicao"] is True and j["data_referencia"] == QUA.isoformat() and j["tipo"] == "GRAVACAO"


def test_gravacao_antecipada_continua_com_data_futura(client, db_session, admin_headers):
    s = _cenario(db_session)
    corpo = _gravacao(s, data="2026-10-26", data_referencia=QUA.isoformat(), grade_exibicao_id=str(s["g"].id),
                      solicitante_antecipacao="SEDUC", chamado="18097")
    r = client.post(f"{AG}/agendamentos", json=corpo, headers=admin_headers)
    assert r.status_code == 201, r.text
    assert r.json()["reposicao"] is False
    # sem reposição, data no passado não vale
    r = client.post(f"{AG}/agendamentos", json=_gravacao(s, data_referencia="2026-10-20", horario_inicio="16:00",
                                                         horario_fim="17:00"), headers=admin_headers)
    assert r.status_code == 422


def test_reposicao_ligada_aparece_para_o_relatorio_da_aula(client, db_session, admin_headers):
    from app.services import agenda_estudios as svc

    s = _cenario(db_session)
    client.post(f"{AG}/agendamentos", json=_gravacao(s, reposicao=True, data_referencia=QUA.isoformat(),
                                                     grade_exibicao_id=str(s["g"].id)), headers=admin_headers)
    r = svc.estudio_da_aula(db_session, s["t"].id, QUA, inicio=time(8, 30))
    rep = r["reposicao_agendada"]
    assert rep and rep["data_gravacao"] == GRAV.isoformat() and rep["estudio_gravacao"] == "ESTÚDIO 2"
    assert r["exibicao_antecipada"] is None


def test_converte_agendamentos_antigos_para_gravacao(db_session, admin_user):
    from app.models.agenda_estudio import converter_tipos_de_gravacao

    s = _cenario(db_session)
    a = AgendamentoEstudio(data=GRAV, estudio_id=s["e1"].id, horario_inicio=time(14, 0), horario_fim=time(15, 0),
                           tipo="REPOSICAO", titulo="Antigo", criado_por=admin_user.id, descricao="faltou")
    b = AgendamentoEstudio(data=GRAV, estudio_id=s["e2"].id, horario_inicio=time(14, 0), horario_fim=time(15, 0),
                           tipo="REGRAVACAO", titulo="Antigo 2", criado_por=admin_user.id)
    db_session.add_all([a, b])
    db_session.commit()
    assert converter_tipos_de_gravacao(db_session.get_bind()) == 2
    db_session.expire_all()
    a, b = db_session.get(AgendamentoEstudio, a.id), db_session.get(AgendamentoEstudio, b.id)
    assert a.tipo == "GRAVACAO" and a.reposicao is True and "[tipo antigo: " in a.descricao and "faltou" in a.descricao
    assert b.tipo == "GRAVACAO" and b.reposicao is False and "[tipo antigo: " in b.descricao
    # rodar de novo não muda nada
    assert converter_tipos_de_gravacao(db_session.get_bind()) == 0


# ─── Relatório do assistente ───────────────────────────────────────────

def test_exibicao_de_aula_gravada_antes_sai_sem_professor(db_session, admin_user):
    from app.api.rotas_report import _professor_da_exibicao

    s = _cenario(db_session)
    cr = _cr(db_session, s, admin_user.id, professor_nome_externo="BIA",
             motivo_referencia="Exibição da aula gravada antecipadamente em 26/10/2026")
    _professor_da_exibicao(cr)
    assert cr.professor_id is None and cr.professor_nome_externo is None
    normal = _cr(db_session, s, admin_user.id, horario_aula="09:30 às 10:30")
    _professor_da_exibicao(normal)
    assert normal.professor_id == s["p"].id


# ─── Fila da coordenação ───────────────────────────────────────────────

def test_fila_da_coordenacao_prontos_e_aguardando(client, db_session, admin_user, admin_headers):
    s = _cenario(db_session)
    pronto = _cr(db_session, s, admin_user.id, video_link="https://drive/v", slide_link="https://drive/p")
    falta = _cr(db_session, s, admin_user.id, horario_aula="09:30 às 10:30", video_link="https://drive/v")
    resumo = client.get("/api/v1/reports/status-resumo", headers=admin_headers).json()
    assert resumo["prontos_para_validar"] == 1 and resumo["aguardando_links"] == 1
    assert "faltam_validar" in resumo  # campo antigo continua para quem usa a API
    lista = client.get("/api/v1/reports/", params={"fila_validacao": "prontos"}, headers=admin_headers).json()
    assert [i["id"] for i in lista["items"]] == [str(pronto.id)]
    assert lista["items"][0]["pronto_para_validar"] is True
    lista = client.get("/api/v1/reports/", params={"fila_validacao": "aguardando"}, headers=admin_headers).json()
    assert [i["id"] for i in lista["items"]] == [str(falta.id)]
    item = lista["items"][0]
    assert item["pronto_para_validar"] is False and "PDF" in item["motivo_espera_validacao"]


# ─── Planilha única e API ──────────────────────────────────────────────

def test_quebra_em_blocos_de_uma_hora_sem_arredondar():
    from app.services.uso_estudio import quebrar_em_horas

    assert quebrar_em_horas("08:00", "10:00") == [("08:00", "09:00", 60), ("09:00", "10:00", 60)]
    assert quebrar_em_horas("07:30", "10:15") == [("07:30", "08:30", 60), ("08:30", "09:30", 60), ("09:30", "10:15", 45)]
    assert quebrar_em_horas("14:00", "14:30") == [("14:00", "14:30", 30)]
    assert quebrar_em_horas("18:30", "19:15") == [("18:30", "19:15", 45)]


def _usos_de_teste(db, s, user_id):
    # evento longo (07:30–10:15) num relatório finalizado
    _cr(db, s, user_id, data_aula=date(2026, 10, 27), horario_aula="07:30 às 10:15", start_time=time(7, 30),
        end_time=time(10, 15), regular="Não", tipo_aula="Videoconferência", professor_id=None)
    # gravação antecipada SEDUC (seg) + exibição (qua)
    _cr(db, s, user_id, data_aula=date(2026, 10, 26), data_execucao_real=date(2026, 10, 26),
        data_referencia_aula=QUA, solicitante_antecipacao="SEDUC", tipo_aula="Gravação estúdio",
        horario_aula="14:00 às 15:00", start_time=time(14, 0), end_time=time(15, 0))
    _cr(db, s, user_id, data_aula=QUA, professor_id=None, solicitante_antecipacao="SEDUC",
        motivo_referencia="Exibição da aula gravada antecipadamente em 26/10/2026")
    # rascunho não entra
    _cr(db, s, user_id, data_aula=date(2026, 10, 29), status="RASCUNHO")


def test_planilha_uso_de_estudio_uma_linha_por_hora(db_session, admin_user):
    from app.services.audit_export import AuditExportFilters
    from app.services.uso_estudio import build_uso_estudio_workbook

    s = _cenario(db_session)
    _usos_de_teste(db_session, s, admin_user.id)
    out = build_uso_estudio_workbook(db_session, AuditExportFilters(data_inicio=date(2026, 10, 1),
                                                                    data_fim=date(2026, 10, 31)), user_role="admin")
    wb = load_workbook(io.BytesIO(out))
    assert wb.sheetnames == ["Uso de Estúdio"]
    ws = wb["Uso de Estúdio"]
    cab = [c.value for c in ws[1]]
    linhas = [dict(zip(cab, [c.value for c in r])) for r in ws.iter_rows(min_row=2)]
    assert len(linhas) == 5  # 3 do evento + gravação + exibição; rascunho fora
    evento = [l for l in linhas if l["DATA"] == "27/10/2026"]
    assert [(l["INÍCIO"], l["FIM"], l["TEMPO (MIN)"], l["BLOCO"]) for l in evento] == [
        ("07:30", "08:30", 60, "1 de 3"), ("08:30", "09:30", 60, "2 de 3"), ("09:30", "10:15", 45, "3 de 3")]
    grav = next(l for l in linhas if l["DATA"] == "26/10/2026")
    assert grav["TIPO DE USO"] == "Gravação antecipada" and grav["COBRAR"] == "Sim" and grav["SEDUC"] == "Sim"
    assert grav["PAGA PROFESSOR"] == "Sim" and grav["REFERÊNCIA"] == "28/10/2026"
    exib = next(l for l in linhas if l["DATA"] == "28/10/2026")
    assert exib["TIPO DE USO"] == "Exibição de aula antecipada" and exib["COBRAR"] == "Sim"
    assert not exib["PROFESSOR"] and exib["PAGA PROFESSOR"] == "Não" and exib["REFERÊNCIA"] == "26/10/2026"


def test_coordenacao_nao_ve_colunas_do_diretor(db_session, admin_user):
    from app.services.audit_export import AuditExportFilters
    from app.services.uso_estudio import build_uso_estudio_workbook

    s = _cenario(db_session)
    _usos_de_teste(db_session, s, admin_user.id)
    out = build_uso_estudio_workbook(db_session, AuditExportFilters(), user_role="coordenador")
    cab = [c.value for c in load_workbook(io.BytesIO(out))["Uso de Estúdio"][1]]
    assert "DIRETOR DE IMAGEM" not in cab and "STATUS DIRETOR" not in cab


def test_api_de_cobranca_devolve_o_tempo_exato(client, db_session, admin_user):
    s = _cenario(db_session)
    _usos_de_teste(db_session, s, admin_user.id)
    params = {"data_inicio": "2026-10-01", "data_fim": "2026-10-31"}
    assert client.get("/api/v1/external/uso-estudio", params=params).status_code == 422  # sem chave
    r = client.get("/api/v1/external/uso-estudio", params=params, headers={"X-API-Key": CHAVE})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["total_usos"] == 3
    evento = next(u for u in j["usos"] if u["data"] == "2026-10-27")
    assert evento["minutos_uso"] == 165 and evento["tempo_uso"] == "2h45" and evento["minutos_cobrados"] == 165
    assert j["minutos_uso"] == 165 + 60 + 60
    so_seduc = client.get("/api/v1/external/uso-estudio", params={**params, "seduc": "true"},
                          headers={"X-API-Key": CHAVE}).json()
    assert {u["tipo_uso"] for u in so_seduc["usos"]} == {"Gravação antecipada", "Exibição de aula antecipada"}


def test_gravacao_antecipada_sem_seduc_nao_cobra_na_api(client, db_session, admin_user):
    s = _cenario(db_session)
    _cr(db_session, s, admin_user.id, data_aula=date(2026, 10, 26), data_execucao_real=date(2026, 10, 26),
        data_referencia_aula=QUA, solicitante_antecipacao="PROFESSOR", tipo_aula="Gravação estúdio")
    j = client.get("/api/v1/external/uso-estudio", params={"data_inicio": "2026-10-01", "data_fim": "2026-10-31"},
                   headers={"X-API-Key": CHAVE}).json()
    assert j["usos"][0]["cobrar"] is False and j["usos"][0]["minutos_cobrados"] == 0


def test_exportacao_padrao_e_restrita(client, db_session, admin_user, admin_headers, assistant_headers):
    s = _cenario(db_session)
    _usos_de_teste(db_session, s, admin_user.id)
    assert client.get("/api/v1/reports/export", headers=assistant_headers).status_code == 403
    r = client.get("/api/v1/reports/export", headers=admin_headers)
    assert r.status_code == 200 and "uso_de_estudio" in r.headers["content-disposition"]
    assert load_workbook(io.BytesIO(r.content)).sheetnames == ["Uso de Estúdio"]
    r = client.get("/api/v1/reports/export", params={"modelo": "detalhado"}, headers=admin_headers)
    assert "Consolidado" in load_workbook(io.BytesIO(r.content)).sheetnames


# ─── Painel do professor ───────────────────────────────────────────────

def test_total_de_aulas_e_horas_do_professor(client, db_session, admin_user, admin_headers):
    s = _cenario(db_session)
    _cr(db_session, s, admin_user.id, data_aula=date(2026, 10, 26))
    _cr(db_session, s, admin_user.id, data_aula=date(2026, 10, 27))
    _cr(db_session, s, admin_user.id, data_aula=date(2026, 10, 28), horario_aula="18:30 às 19:15",
        start_time=time(18, 30), end_time=time(19, 15), turno="Noite")
    _cr(db_session, s, admin_user.id, data_aula=date(2026, 10, 29), status="CANCELADO")
    r = client.get("/api/v1/reports/professor-resumo", params={"professor_id": str(s["p"].id)}, headers=admin_headers)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["total_aulas"] == 3 and j["total_minutos"] == 165 and j["total_horas"] == "2h45"


# ─── Gravação da grade (MP) ────────────────────────────────────────────

def test_gravacao_da_grade_muda_de_horario_no_dia(client, db_session, admin_headers):
    from app.services import agenda_estudios as svc

    s = _cenario(db_session, tipo_slot="gravacao")
    corpo = {"data": QUA.isoformat(), "grade_id": str(s["g"].id), "estudio_destino_id": s["e1"].id,
             "horario_inicio": "15:00", "horario_fim": "16:00"}
    r = client.post(f"{AG}/aulas/remanejar", json=corpo, headers=admin_headers)
    assert r.status_code == 201, r.text
    aula = next(a for a in svc.aulas_do_dia(db_session, QUA) if a["grade_id"] == str(s["g"].id))
    assert aula["inicio"] == time(15, 0) and aula["fim"] == time(16, 0) and aula["inicio_grade"] == time(8, 30)
    # o relatório aberto pelo horário da grade ainda acha a aula (e o horário do dia)
    r = svc.estudio_da_aula(db_session, s["t"].id, QUA, inicio=time(8, 30))
    assert r["encontrado"] and r["inicio"] == "15:00"
    # voltar ao original
    assert client.post(f"{AG}/aulas/restaurar", json={"data": QUA.isoformat(), "grade_id": str(s["g"].id)},
                       headers=admin_headers).status_code == 200


def test_aula_da_grade_nao_muda_de_horario(client, db_session, admin_headers):
    s = _cenario(db_session, tipo_slot="aula")
    corpo = {"data": QUA.isoformat(), "grade_id": str(s["g"].id), "estudio_destino_id": s["e2"].id,
             "horario_inicio": "15:00", "horario_fim": "16:00"}
    r = client.post(f"{AG}/aulas/remanejar", json=corpo, headers=admin_headers)
    assert r.status_code == 422 and "gravação" in r.json()["detail"].lower()
    # só trocar de estúdio continua valendo
    corpo.pop("horario_inicio"), corpo.pop("horario_fim")
    assert client.post(f"{AG}/aulas/remanejar", json=corpo, headers=admin_headers).status_code == 201


def test_gravacao_da_grade_sem_estudio_fica_na_faixa_e_pode_ser_encaixada(client, db_session, admin_headers):
    """MP sem estúdio na grade: aparece na faixa do turno (não como aviso) e o chefe encaixa num estúdio."""
    from app.services import agenda_estudios as svc

    s = _cenario(db_session, tipo_slot="gravacao")
    s["g"].estudio_id = None
    db_session.commit()
    dia = client.get(f"{AG}/dia", params={"data": QUA.isoformat()}, headers=admin_headers).json()
    manha = next(t for t in dia["turnos"] if t["turno"] == "manha")
    assert [g["grade_id"] for g in manha["gravacoes_sem_estudio"]] == [str(s["g"].id)]
    assert manha["gravacoes_sem_estudio"][0]["gravacao"] is True
    assert not any("sem estúdio definido" in c["mensagem"] for c in dia["conferencia"])
    corpo = {"data": QUA.isoformat(), "grade_id": str(s["g"].id), "estudio_destino_id": s["e2"].id,
             "horario_inicio": "10:00", "horario_fim": "11:00"}
    assert client.post(f"{AG}/aulas/remanejar", json=corpo, headers=admin_headers).status_code == 201
    dia = client.get(f"{AG}/dia", params={"data": QUA.isoformat()}, headers=admin_headers).json()
    manha = next(t for t in dia["turnos"] if t["turno"] == "manha")
    assert manha["gravacoes_sem_estudio"] == []
    col = next(c for c in manha["estudios"] if c["estudio_id"] == s["e2"].id)
    it = next(i for i in col["itens"] if i.get("grade_id") == str(s["g"].id))
    assert it["inicio"] == "10:00" and it["gravacao"] and it["horario_mudou"]
    r = svc.estudio_da_aula(db_session, s["t"].id, QUA, inicio=time(8, 30))
    assert r["encontrado"] and r["estudio"] == "ESTÚDIO 2"
    # tirar do estúdio: volta para a faixa
    assert client.post(f"{AG}/aulas/restaurar", json={"data": QUA.isoformat(), "grade_id": str(s["g"].id)},
                       headers=admin_headers).status_code == 200
    dia = client.get(f"{AG}/dia", params={"data": QUA.isoformat()}, headers=admin_headers).json()
    assert next(t for t in dia["turnos"] if t["turno"] == "manha")["gravacoes_sem_estudio"]
