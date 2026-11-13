"""
Canal Educação v4.1 — modo sem worker (Vercel): configuração, rotas de sistema
e busca no Drive rodando direto na API.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.config import Settings, get_settings
from app.models.class_report import ClassReport
from tests.conftest import TestingSessionLocal


def test_plataforma_padrao_e_docker(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    s = Settings()
    assert (s.eh_vercel, s.modo_tarefas, s.tempo_real) == (False, "celery", True)


def test_vercel_detectada_pela_variavel(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    s = Settings()
    assert (s.eh_vercel, s.modo_tarefas, s.tempo_real) == (True, "direto", False)


def test_modo_tarefas_pode_ser_forcado(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("MODO_TAREFAS", "celery")
    assert Settings().modo_tarefas == "celery"


def test_saude(client):
    r = client.get("/api/v1/sistema/saude")
    assert r.status_code == 200
    assert r.json()["api"] == "ok"


@pytest.fixture
def segredo(monkeypatch):
    monkeypatch.setattr(get_settings(), "CRON_SECRET", "segredo-de-teste-123")
    return {"Authorization": "Bearer segredo-de-teste-123"}


def test_rotas_de_sistema_fechadas_sem_segredo(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "CRON_SECRET", "")
    assert client.post("/api/v1/sistema/varredura").status_code == 403
    assert client.post("/api/v1/sistema/migrar").status_code == 403


def test_rotas_de_sistema_recusam_segredo_errado(client, segredo):
    r = client.get("/api/v1/sistema/varredura", headers={"Authorization": "Bearer outro"})
    assert r.status_code == 401


def _relatorio(db, criado_ha_horas, **kw):
    cr = ClassReport(
        id=uuid.uuid4(), created_by=uuid.uuid4(), status="AGUARDANDO_VALIDACAO",
        data_aula=date.today() - timedelta(days=1), turno="MANHÃ", estudio="Estúdio 01",
        turma_id=uuid.uuid4(), disciplina_id=uuid.uuid4(), professor_id=uuid.uuid4(),
        horario_aula="08:00 às 09:00", tipo_aula="Transmissão ao vivo", canal_utilizado="1",
        conteudo_ministrado="X", status_compliance="Pendente",
        nome_ficheiro_gerado=f"EM 1 TIM - MAT - {uuid.uuid4().hex[:6]}",
        **kw,
    )
    db.add(cr)
    db.commit()
    cr.created_at = datetime.now(timezone.utc) - timedelta(hours=criado_ha_horas)
    db.commit()
    return cr.id


@pytest.fixture
def modo_direto(monkeypatch):
    """Simula a Vercel: tarefas diretas, sessão do worker no banco de teste, Drive falso."""
    from app.tasks import worker

    monkeypatch.setattr(get_settings(), "MODO_TAREFAS", "direto")
    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    # o diretor de imagem não bloqueia nestes testes
    monkeypatch.setattr("app.services.busca_links.bloqueio_busca_link", lambda *a, **k: None)
    achados = {}

    def video(nome):
        return achados.get(("video", nome))

    def pdf(nome):
        return achados.get(("pdf", nome))

    monkeypatch.setattr(worker, "buscar_video_no_drive", video)
    monkeypatch.setattr(worker, "buscar_slide_no_drive", pdf)
    return achados


def test_varredura_direta_acha_arquivos_e_marca_verde(client, segredo, modo_direto, db_session):
    rid = _relatorio(db_session, criado_ha_horas=5)
    nome = db_session.get(ClassReport, rid).nome_ficheiro_gerado
    modo_direto[("video", nome)] = {"webViewLink": "https://drive/v", "size": 500 * 1024 * 1024, "md5Checksum": "x"}
    modo_direto[("pdf", nome)] = {"webViewLink": "https://drive/p"}

    r = client.get("/api/v1/sistema/varredura", headers=segredo)
    assert r.status_code == 200, r.text
    assert r.json()["modo"] == "direto" and r.json()["verdes"] == 1

    db_session.expire_all()
    cr = db_session.get(ClassReport, rid)
    assert cr.status_compliance == "Verde"
    assert cr.video_link == "https://drive/v" and cr.slide_link == "https://drive/p"
    assert cr.compliance_verificado_em is not None


def test_varredura_direta_respeita_espera_inicial(client, segredo, modo_direto, db_session):
    _relatorio(db_session, criado_ha_horas=0.5)  # finalizado há pouco: o arquivo ainda não chegou
    r = client.post("/api/v1/sistema/varredura", headers=segredo)
    assert r.json()["na_lista"] == 0


def test_varredura_direta_marca_vermelho_depois_do_prazo(client, segredo, modo_direto, db_session):
    s = get_settings()
    prazo_h = (s.COMPLIANCE_INITIAL_DELAY_SECONDS + s.COMPLIANCE_MAX_RETRIES * s.COMPLIANCE_RETRY_INTERVAL_SECONDS) / 3600
    rid = _relatorio(db_session, criado_ha_horas=prazo_h + 1)
    r = client.post("/api/v1/sistema/varredura", headers=segredo)
    assert r.json()["vermelhos"] == 1
    db_session.expire_all()
    assert db_session.get(ClassReport, rid).status_compliance == "Vermelho"


def test_botao_buscar_no_drive_roda_na_hora_sem_worker(client, admin_headers, modo_direto, db_session):
    _relatorio(db_session, criado_ha_horas=5)
    r = client.post("/api/v1/reports/force-sync-drive", headers=admin_headers)
    assert r.status_code == 202, r.text
    assert r.json()["detalhes"]["modo"] == "direto"
    assert "Busca no Drive feita" in r.json()["message"]


def test_finalizar_sem_worker_nao_usa_celery(monkeypatch):
    from app.services import tarefas
    from app.tasks import worker

    monkeypatch.setattr(get_settings(), "MODO_TAREFAS", "direto")

    def proibido(*a, **k):
        raise AssertionError("não deveria usar a fila")

    monkeypatch.setattr(worker.verificar_compliance_drive, "apply_async", proibido)
    tarefas.agendar_verificacao(uuid.uuid4(), "qualquer")


def test_pagina_sem_tempo_real_avisa_o_front(client, monkeypatch):
    from app.main import templates

    monkeypatch.setitem(templates.env.globals, "tempo_real", False)
    assert "window.CANAL_TEMPO_REAL = false" in client.get("/inicio").text
