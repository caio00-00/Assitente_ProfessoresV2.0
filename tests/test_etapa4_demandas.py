"""
Canal Educação v3.0 — Testes Automatizados Etapa 4:
- Item 6: Campo obrigatório "Nome do Evento" em agendamentos do tipo EVENTO
- Item 8: Campo "Chave de Transmissão" no agendamento e relatório do Diretor de Imagem
- Demanda 2.4: Lookup de contexto do estúdio e permissão de consulta para Diretor de Imagem
"""

from datetime import date, time
import uuid
import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.agenda_estudio import AgendamentoEstudio
from app.models.infraestrutura import Estudio
from app.models.user import User


@pytest.fixture
def diretor_imagem_headers(db_session):
    user = User(
        email=f"di_{uuid.uuid4().hex[:6]}@test.com",
        full_name="Diretor de Imagem Teste",
        role="diretor_imagem",
        hashed_password=get_password_hash("di123"),
        email_confirmed=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = create_access_token(
        data={
            "sub": user.email,
            "role": user.role,
            "user_id": str(user.id),
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_agendamento_evento_obriga_nome_evento(client, admin_headers, db_session):
    est = db_session.query(Estudio).first()
    if not est:
        est = Estudio(nome="Estúdio 01", ativo=True, horario_inicio=time(7, 0), horario_fim=time(22, 0))
        db_session.add(est)
        db_session.commit()

    # Tentativa de criar agendamento EVENTO sem nome_evento deve falhar com 422
    payload_invalido = {
        "data": date.today().isoformat(),
        "estudio_id": est.id,
        "horario_inicio": "14:00",
        "horario_fim": "15:00",
        "tipo": "EVENTO",
        "titulo": " ",
        "nome_evento": None,
    }
    r = client.post("/api/v1/agenda-estudios/agendamentos", json=payload_invalido, headers=admin_headers)
    assert r.status_code == 422
    assert "Nome do Evento" in r.text or "titulo" in r.text

    # Com nome_evento e chave_transmissao deve salvar com sucesso 201
    payload_valido = {
        "data": date.today().isoformat(),
        "estudio_id": est.id,
        "horario_inicio": "14:00",
        "horario_fim": "15:00",
        "tipo": "EVENTO",
        "titulo": "Live SEDUC",
        "nome_evento": "Live SEDUC Jogos Escolares",
        "departamento": "UETEV",
        "chave_transmissao": "live-stream-key-xyz-123",
        "chamado": "20261018",
    }
    r2 = client.post("/api/v1/agenda-estudios/agendamentos", json=payload_valido, headers=admin_headers)
    assert r2.status_code == 201
    dados = r2.json()
    assert dados["nome_evento"] == "Live SEDUC Jogos Escolares"
    assert dados["chave_transmissao"] == "live-stream-key-xyz-123"


def test_lookup_contexto_estudio(client, admin_headers, db_session):
    est = db_session.query(Estudio).first()
    if not est:
        est = Estudio(nome="Estúdio 01", ativo=True, horario_inicio=time(7, 0), horario_fim=time(22, 0))
        db_session.add(est)
        db_session.commit()

    # Cadastra evento com chave
    ev = AgendamentoEstudio(
        data=date.today(),
        estudio_id=est.id,
        horario_inicio=time(14, 0),
        horario_fim=time(16, 0),
        tipo="EVENTO",
        titulo="Encontro Regional",
        nome_evento="Encontro Regional SEDUC",
        departamento="SUGED",
        chave_transmissao="key-12345-stream",
        chamado="5544",
        status="AGENDADO",
    )
    db_session.add(ev)
    db_session.commit()

    r = client.get(
        f"/api/v1/image-director/lookup/contexto-estudio?data={date.today().isoformat()}&turno=Tarde&estudio={est.nome}",
        headers=admin_headers,
    )
    assert r.status_code == 200
    dados = r.json()
    assert dados["is_evento"] is True
    assert dados["nome_evento"] == "Encontro Regional SEDUC"
    assert dados["chave_transmissao"] == "key-12345-stream"
    assert dados["departamento"] == "SUGED"


def test_diretor_imagem_pode_consultar_contexto_estudio(client, diretor_imagem_headers, db_session):
    est = db_session.query(Estudio).first()
    if not est:
        est = Estudio(nome="Estúdio 01", ativo=True, horario_inicio=time(7, 0), horario_fim=time(22, 0))
        db_session.add(est)
        db_session.commit()

    r = client.get(
        f"/api/v1/image-director/lookup/contexto-estudio?data={date.today().isoformat()}&turno=Tarde&estudio={est.nome}",
        headers=diretor_imagem_headers,
    )
    assert r.status_code == 200
    dados = r.json()
    assert "diretor_imagem_id" in dados
    assert "chave_transmissao" in dados
