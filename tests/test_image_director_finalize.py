"""Tests for image director report finalize flow."""

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.diretor_imagem import DiretorImagem
from app.models.user import User
from app.schemas.image_director_report import ImageDirectorReportCreate


def _diretor_headers(db_session, sample_turma):
    user = User(
        email="diretor_imagem@test.com",
        full_name="Diretor Imagem Test",
        role="diretor_imagem",
        hashed_password=get_password_hash("test123"),
        email_confirmed=True,
    )
    db_session.add(user)
    db_session.flush()
    diretor = DiretorImagem(nome="Diretor Imagem Test", user_id=user.id, is_active=True)
    db_session.add(diretor)
    db_session.commit()

    token = create_access_token(
        data={"sub": user.email, "role": user.role, "user_id": str(user.id)}
    )
    return {"Authorization": f"Bearer {token}"}, diretor


def test_finalize_report_sets_aguardando_validacao(client, db_session, sample_turma):
    headers, diretor = _diretor_headers(db_session, sample_turma)

    create_payload = {
        "diretor_imagem_id": str(diretor.id),
        "data_relatorio": "2026-09-08",
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "turma_id": str(sample_turma.id),
        "disciplina_nome": "Matemática",
        "professor_nome_externo": "Prof Test",
        "horario_aula": "07:30 - 08:30",
        "youtube_link": "https://youtube.com/watch?v=test123",
        "origem": "grade",
    }
    created = client.post("/api/v1/image-director/", json=create_payload, headers=headers)
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    lesson_payload = {
        "disciplina_nome": "Matemática",
        "professor_nome": "Prof Test",
        "transmissao_ou_gravada": "Transmissão",
        "canal_utilizado": "1",
    }
    lesson = client.post(
        f"/api/v1/image-director/{report_id}/lessons",
        json=lesson_payload,
        headers=headers,
    )
    assert lesson.status_code == 201, lesson.text

    finalized = client.post(
        f"/api/v1/image-director/{report_id}/finalize",
        json={"youtube_link": "https://youtube.com/watch?v=test123"},
        headers=headers,
    )
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["status"] == "AGUARDANDO_VALIDACAO"

    listed = client.get(
        "/api/v1/image-director/?status=AGUARDANDO_VALIDACAO", headers=headers
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == report_id


def test_finalize_without_youtube_returns_422(client, db_session, sample_turma):
    headers, diretor = _diretor_headers(db_session, sample_turma)

    create_payload = {
        "diretor_imagem_id": str(diretor.id),
        "data_relatorio": "2026-09-08",
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "turma_id": str(sample_turma.id),
        "disciplina_nome": "Matemática",
        "professor_nome_externo": "Prof Test",
        "horario_aula": "07:30 - 08:30",
        "origem": "grade",
    }
    created = client.post("/api/v1/image-director/", json=create_payload, headers=headers)
    assert created.status_code == 201
    report_id = created.json()["id"]

    client.post(
        f"/api/v1/image-director/{report_id}/lessons",
        json={
            "disciplina_nome": "Matemática",
            "professor_nome": "Prof Test",
            "transmissao_ou_gravada": "Transmissão",
            "canal_utilizado": "1",
        },
        headers=headers,
    )

    finalized = client.post(
        f"/api/v1/image-director/{report_id}/finalize",
        json={},
        headers=headers,
    )
    assert finalized.status_code == 422


def test_list_reports_filter_transmissao_ou_gravada(client, db_session, sample_turma):
    headers, diretor = _diretor_headers(db_session, sample_turma)

    def _create_with_lesson(transmissao_ou_gravada, horario_aula="07:30 - 08:30"):
        created = client.post(
            "/api/v1/image-director/",
            json={
                "diretor_imagem_id": str(diretor.id),
                "data_relatorio": "2026-09-09",
                "turno": "Manhã",
                "estudio": "Estúdio 01",
                "turma_id": str(sample_turma.id),
                "disciplina_nome": "Matemática",
                "professor_nome_externo": "Prof Test",
                "horario_aula": horario_aula,
                "origem": "grade",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        report_id = created.json()["id"]
        lesson = client.post(
            f"/api/v1/image-director/{report_id}/lessons",
            json={
                "disciplina_nome": "Matemática",
                "professor_nome": "Prof Test",
                "transmissao_ou_gravada": transmissao_ou_gravada,
                "canal_utilizado": "1" if transmissao_ou_gravada == "Transmissão" else None,
            },
            headers=headers,
        )
        assert lesson.status_code == 201, lesson.text
        return report_id

    id_transmissao = _create_with_lesson("Transmissão", "07:30 - 08:30")
    id_gravada = _create_with_lesson("Aula gravada", "08:30 - 09:30")

    res_transmissao = client.get(
        "/api/v1/image-director/?transmissao_ou_gravada=Transmissão",
        headers=headers,
    )
    assert res_transmissao.status_code == 200
    ids_transmissao = {item["id"] for item in res_transmissao.json()["items"]}
    assert id_transmissao in ids_transmissao
    assert id_gravada not in ids_transmissao

    res_gravada = client.get(
        "/api/v1/image-director/?transmissao_ou_gravada=Aula%20gravada",
        headers=headers,
    )
    assert res_gravada.status_code == 200
    ids_gravada = {item["id"] for item in res_gravada.json()["items"]}
    assert id_gravada in ids_gravada
    assert id_transmissao not in ids_gravada


def test_schema_nao_aceita_mais_nova_aula():
    import pytest
    with pytest.raises(ValueError):
        ImageDirectorReportCreate.valid_origem("nova_aula")
    assert ImageDirectorReportCreate.valid_origem("evento") == "evento"


def test_schema_rejects_invalid_origem():
    with pytest.raises(ValueError, match="origem deve ser um de"):
        ImageDirectorReportCreate.valid_origem("invalido")


def test_evento_sem_turma_nem_professor(client, db_session, sample_turma):
    """Evento (UETEV, SUGED…): sem turma/professor, com departamento, horário e chamado."""
    headers, diretor = _diretor_headers(db_session, sample_turma)
    base = {
        "diretor_imagem_id": str(diretor.id),
        "data_relatorio": "2026-09-08",
        "turno": "Tarde",
        "estudio": "Estúdio 09",
        "disciplina_nome": "Formação de professores",
        "serie_modulo_manual": "EVENTO · SUGED",
        "horario_aula": "14:00 às 16:00",
        "regular": "Não",
        "ticket_number": "18097",
        "start_time": "14:00",
        "end_time": "16:00",
        "youtube_link": "https://youtube.com/watch?v=evento",
        "origem": "evento",
    }
    created = client.post("/api/v1/image-director/", json=base, headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["origem"] == "evento" and body["turma_id"] is None and body["ticket_number"] == "18097"

    # Sem chamado ou sem departamento: recusa
    sem_chamado = client.post("/api/v1/image-director/", json={**base, "ticket_number": None,
                                                               "data_relatorio": "2026-09-09"}, headers=headers)
    assert sem_chamado.status_code == 422
    sem_dep = client.post("/api/v1/image-director/", json={**base, "serie_modulo_manual": None,
                                                           "data_relatorio": "2026-09-10"}, headers=headers)
    assert sem_dep.status_code == 422

    # Pode finalizar com um bloco técnico
    rid = body["id"]
    client.post(f"/api/v1/image-director/{rid}/lessons", json={
        "disciplina_nome": "Formação de professores", "professor_nome": "SUGED",
        "transmissao_ou_gravada": "Transmissão", "canal_utilizado": "9",
    }, headers=headers)
    fin = client.post(f"/api/v1/image-director/{rid}/finalize", json={}, headers=headers)
    assert fin.status_code == 200, fin.text
    assert fin.json()["status"] == "AGUARDANDO_VALIDACAO"
