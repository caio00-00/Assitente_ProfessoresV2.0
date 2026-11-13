"""
Canal Educação v4 — testes das regras novas e das telas Início / Linha do tempo.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app.domain import estados, politicas
from app.models.class_report import ClassReport
from app.models.historico import ReportVersion
from app.services.audit_export import cobrar_conforme_status


# ─── Política de permissões ──────────────────────────────────────────

class _U:
    def __init__(self, role, uid=None):
        self.role = role
        self.id = uid or uuid.uuid4()


def test_normalizar_papel_coordenadora():
    assert politicas.normalizar_papel("Coordenadora") == "coordenador"
    assert politicas.normalizar_papel(" ADMIN ") == "admin"


@pytest.mark.parametrize("papel", ["diretor_imagem", "diretor_chefe", "auditor"])
def test_quem_nao_escreve_relatorio_de_aula(papel):
    assert not politicas.pode(_U(papel), "relatorio_aula.criar")


def test_assistente_so_mexe_no_proprio():
    eu = _U("assistente")
    assert politicas.pode(eu, "relatorio_aula.editar", autor_id=eu.id)
    assert not politicas.pode(eu, "relatorio_aula.editar", autor_id=uuid.uuid4())
    with pytest.raises(HTTPException) as e:
        politicas.exigir(eu, "relatorio_aula.cancelar", autor_id=uuid.uuid4())
    assert e.value.status_code == 403


def test_coordenacao_edita_de_qualquer_um():
    assert politicas.pode(_U("coordenador"), "relatorio_aula.editar", autor_id=uuid.uuid4())


def test_so_coordenacao_valida():
    assert politicas.pode(_U("coordenador"), "relatorio_aula.validar")
    assert not politicas.pode(_U("assistente"), "relatorio_aula.validar")


# ─── Máquina de estados ──────────────────────────────────────────────

def test_transicoes_principais():
    assert estados.destino("finalizar", "RASCUNHO") == "AGUARDANDO_VALIDACAO"
    assert estados.destino("validar", "AGUARDANDO_VALIDACAO") == "VALIDADO"
    assert estados.destino("devolver", "VALIDADO") == "RASCUNHO"
    assert estados.destino("cancelar", "VALIDADO") == "CANCELADO"
    assert estados.destino("validar", "FINALIZADO") == "VALIDADO"  # legado


@pytest.mark.parametrize("acao,status", [
    ("finalizar", "VALIDADO"),
    ("validar", "RASCUNHO"),
    ("cancelar", "CANCELADO"),
    ("devolver", "CANCELADO"),
])
def test_transicoes_proibidas(acao, status):
    with pytest.raises(HTTPException) as e:
        estados.destino(acao, status)
    assert e.value.status_code == 400


# ─── Faturamento conforme status ─────────────────────────────────────

class _R:
    def __init__(self, status):
        self.status = status


def test_cobrar_pendente_enquanto_nao_validado():
    assert cobrar_conforme_status(_R("AGUARDANDO_VALIDACAO"), _R("VALIDADO"), "Sim").startswith("Pendente")


def test_cobrar_cancelado():
    assert cobrar_conforme_status(_R("CANCELADO"), None, "Sim") == "Não (cancelado)"


def test_cobrar_validado_usa_regra():
    assert cobrar_conforme_status(_R("VALIDADO"), _R("VALIDADO"), "Sim") == "Sim"


# ─── API: criar, editar, histórico, exclusão ─────────────────────────

def _payload(turma, pd, **extra):
    base = {
        "data_aula": date.today().isoformat(),
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "turma_id": str(turma.id),
        "disciplina_id": str(pd["disciplina"].id),
        "professor_id": str(pd["professor"].id),
        "horario_aula": "07:30 - 08:30",
        "regular": "Sim",
        "tipo_aula": "Transmissão ao vivo",
        "canal_utilizado": "1",
        "conteudo_ministrado": "Funções",
        "youtube_link": "https://youtube.com/watch?v=123",
        "bncc_habilidades": "EF09MA01",
        "tipo_recursos_utilizados": ["Quadro digital"],
    }
    base.update(extra)
    return base


def test_criar_registra_versao(client, admin_headers, db_session, sample_turma, sample_professor_disciplina):
    res = client.post("/api/v1/reports/", json=_payload(sample_turma, sample_professor_disciplina), headers=admin_headers)
    assert res.status_code == 201, res.text
    rid = uuid.UUID(res.json()["id"])
    versoes = db_session.query(ReportVersion).filter(ReportVersion.report_id == rid).all()
    assert [v.evento for v in versoes] == ["CRIADO"]


def test_editar_nao_apaga_pdf_coletado(client, admin_headers, db_session, sample_turma, sample_professor_disciplina):
    """Bug v3: o formulário não envia slide_link e a edição gravava None."""
    res = client.post("/api/v1/reports/", json=_payload(sample_turma, sample_professor_disciplina), headers=admin_headers)
    rid = res.json()["id"]
    cr = db_session.query(ClassReport).filter(ClassReport.id == uuid.UUID(rid)).first()
    cr.slide_link = "https://drive.google.com/file/d/pdf"
    db_session.commit()

    corpo = _payload(sample_turma, sample_professor_disciplina, conteudo_ministrado="Funções revisadas")
    res = client.put(f"/api/v1/reports/{rid}", json=corpo, headers=admin_headers)
    assert res.status_code == 200, res.text
    db_session.expire_all()
    cr = db_session.query(ClassReport).filter(ClassReport.id == uuid.UUID(rid)).first()
    assert cr.slide_link == "https://drive.google.com/file/d/pdf"


def test_assistente_nao_preenche_slide_link(client, assistant_headers, db_session, sample_turma, sample_professor_disciplina):
    corpo = _payload(sample_turma, sample_professor_disciplina, slide_link="https://exemplo/qualquer")
    res = client.post("/api/v1/reports/", json=corpo, headers=assistant_headers)
    assert res.status_code == 201, res.text
    cr = db_session.query(ClassReport).filter(ClassReport.id == uuid.UUID(res.json()["id"])).first()
    assert not cr.slide_link


def test_assistente_nao_exclui_finalizado(client, assistant_headers, assistant_user, db_session, sample_turma):
    cr = ClassReport(
        id=uuid.uuid4(), created_by=assistant_user.id, status="AGUARDANDO_VALIDACAO",
        data_aula=date.today(), turno="MANHÃ", estudio="Estúdio 01", turma_id=sample_turma.id, disciplina_id=uuid.uuid4(), professor_id=uuid.uuid4(),
        horario_aula="08:00 às 09:00", tipo_aula="Transmissão ao vivo", canal_utilizado="1", conteudo_ministrado="X",
        status_compliance="Pendente",
    )
    db_session.add(cr)
    db_session.commit()
    res = client.delete(f"/api/v1/reports/{cr.id}", headers=assistant_headers)
    assert res.status_code == 409


def test_cancelar_guarda_justificativa_sem_apagar_observacoes(client, admin_headers, admin_user, db_session, sample_turma):
    cr = ClassReport(
        id=uuid.uuid4(), created_by=admin_user.id, status="RASCUNHO",
        data_aula=date.today(), turno="MANHÃ", estudio="Estúdio 01", turma_id=sample_turma.id, disciplina_id=uuid.uuid4(), professor_id=uuid.uuid4(),
        horario_aula="08:00 às 09:00", tipo_aula="Transmissão ao vivo", canal_utilizado="1", conteudo_ministrado="X",
        observacoes="Observação original", status_compliance="Pendente",
    )
    db_session.add(cr)
    db_session.commit()
    res = client.patch(f"/api/v1/reports/{cr.id}/cancelar", headers=admin_headers, json={"descricao": "Aula não aconteceu"})
    if res.status_code == 422:
        res = client.patch(f"/api/v1/reports/{cr.id}/cancelar", headers=admin_headers, json={"justificativa": "Aula não aconteceu"})
    assert res.status_code == 200, res.text
    db_session.expire_all()
    cr = db_session.query(ClassReport).filter(ClassReport.id == cr.id).first()
    assert cr.status == "CANCELADO"
    assert cr.observacoes == "Observação original"
    assert "não aconteceu" in (cr.justificativa_cancelamento or "")
    assert cr.cancelado_em is not None

    hist = client.get(f"/api/v1/historico/class_report/{cr.id}", headers=admin_headers)
    assert hist.status_code == 200
    assert any(v["evento"] == "CANCELADO" for v in hist.json()["versoes"])


# ─── Painel Início e linha do tempo ──────────────────────────────────

def test_paginas_v4_renderizam(client):
    for url in ("/inicio", "/aula?cr=" + str(uuid.uuid4())):
        res = client.get(url)
        assert res.status_code == 200
        assert "Canal Educação" in res.text


def test_painel_inicio_assistente(client, assistant_headers, assistant_user, db_session, sample_turma):
    db_session.add(ClassReport(
        id=uuid.uuid4(), created_by=assistant_user.id, status="RASCUNHO", precisa_correcao=True,
        observacao_coordenacao="Corrigir conteúdo", data_aula=date.today(), turno="MANHÃ",
        estudio="Estúdio 01", turma_id=sample_turma.id, disciplina_id=uuid.uuid4(), professor_id=uuid.uuid4(), horario_aula="08:00 às 09:00",
        tipo_aula="Transmissão ao vivo", canal_utilizado="1", conteudo_ministrado="X", status_compliance="Pendente",
    ))
    db_session.commit()
    res = client.get("/api/v1/painel/inicio", headers=assistant_headers)
    assert res.status_code == 200, res.text
    grupos = {g["titulo"]: g for g in res.json()["grupos"]}
    assert grupos["Devolvidos para corrigir"]["total"] == 1
    assert grupos["Devolvidos para corrigir"]["itens"][0]["observacao_coordenacao"] == "Corrigir conteúdo"


def test_painel_inicio_coordenacao(client, admin_headers):
    res = client.get("/api/v1/painel/inicio?dias=30", headers=admin_headers)
    assert res.status_code == 200
    titulos = [g["titulo"] for g in res.json()["grupos"]]
    assert "Prontos para validar" in titulos


def test_linha_do_tempo(client, admin_headers, admin_user, db_session, sample_turma):
    cr = ClassReport(
        id=uuid.uuid4(), created_by=admin_user.id, status="AGUARDANDO_VALIDACAO",
        data_aula=date.today(), turno="MANHÃ", estudio="Estúdio 01", turma_id=sample_turma.id, disciplina_id=uuid.uuid4(), professor_id=uuid.uuid4(),
        horario_aula="08:00 às 09:00", tipo_aula="Transmissão ao vivo", canal_utilizado="1", conteudo_ministrado="X",
        status_compliance="Pendente",
    )
    db_session.add(cr)
    db_session.commit()
    res = client.get(f"/api/v1/aulas/linha-do-tempo?class_report_id={cr.id}", headers=admin_headers)
    assert res.status_code == 200, res.text
    d = res.json()
    chaves = [e["chave"] for e in d["etapas"]]
    assert chaves[0] == "assistente" and "faturamento" in chaves
    assert d["aula"]["cobrar"].startswith("Pendente")


def test_linha_do_tempo_de_outro_assistente_e_proibida(client, assistant_headers, db_session, sample_turma):
    cr = ClassReport(
        id=uuid.uuid4(), created_by=uuid.uuid4(), status="RASCUNHO",
        data_aula=date.today(), turno="MANHÃ", estudio="Estúdio 01", turma_id=sample_turma.id, disciplina_id=uuid.uuid4(), professor_id=uuid.uuid4(),
        horario_aula="08:00 às 09:00", tipo_aula="Transmissão ao vivo", canal_utilizado="1", conteudo_ministrado="X",
        status_compliance="Pendente",
    )
    db_session.add(cr)
    db_session.commit()
    res = client.get(f"/api/v1/aulas/linha-do-tempo?class_report_id={cr.id}", headers=assistant_headers)
    assert res.status_code == 403


# ─── Login ───────────────────────────────────────────────────────────

def test_login_aceita_email_com_maiusculas(client, admin_user):
    res = client.post("/api/v1/auth/login", data={"username": "ADMIN@test.com", "password": "admin123"})
    assert res.status_code == 200


def test_login_bloqueia_apos_muitas_tentativas(client, admin_user):
    from app.core.config import get_settings
    limite = get_settings().LOGIN_MAX_ATTEMPTS
    for _ in range(limite):
        client.post("/api/v1/auth/login", data={"username": "admin@test.com", "password": "errada"})
    res = client.post("/api/v1/auth/login", data={"username": "admin@test.com", "password": "admin123"})
    assert res.status_code == 429
