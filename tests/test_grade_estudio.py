"""
Canal Educação v3.0 — Tests: Grade Horária por Estúdio & Integração com Agenda (Demanda Item 7)
"""

from datetime import date, time, timedelta
import pytest
from app.models.auxiliares import Grade
from app.models.infraestrutura import Estudio
from app.models.agenda_estudio import AgendamentoEstudio


def test_grade_estudio_endpoints(client, admin_headers, db_session, sample_turma, sample_professor_disciplina):
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]

    # 1. Obter ou criar um estúdio ativo
    estudio = db_session.query(Estudio).filter(Estudio.ativo == True).first()
    if not estudio:
        estudio = Estudio(
            nome="Estúdio Teste 01",
            horario_inicio=time(7, 0),
            horario_fim=time(22, 0),
            ativo=True,
        )
        db_session.add(estudio)
        db_session.commit()

    segunda = date(2026, 10, 19)
    domingo = segunda + timedelta(days=6)

    # 2. Criar slot fixo na grade vinculado a este estúdio na segunda-feira (dia_semana=0)
    slot_fixo = Grade(
        turma_id=sample_turma.id,
        disciplina_id=disc.id,
        professor_id=prof.id,
        estudio_id=estudio.id,
        dia_semana=0,
        horario_inicio=time(8, 0),
        horario_fim=time(9, 0),
        turno_aula="MANHÃ",
        canal_iptv=1,
        versao="Grade Teste",
    )
    db_session.add(slot_fixo)

    # 3. Criar agendamento de EVENTO na terça-feira (2026-10-20)
    evento = AgendamentoEstudio(
        data=date(2026, 10, 20),
        estudio_id=estudio.id,
        horario_inicio=time(10, 0),
        horario_fim=time(11, 30),
        tipo="EVENTO",
        titulo="Encontro Pedagógico SEDUC",
        nome_evento="Seminário Estadual",
        departamento="UETEV",
        chamado="CH-9876",
        status="AGENDADO",
    )
    db_session.add(evento)
    db_session.commit()

    # 4. Testar endpoint /api/v1/turmas/grade-estudio/{id}
    res = client.get(
        f"/api/v1/turmas/grade-estudio/{estudio.id}?data_inicio={segunda}&data_fim={domingo}",
        headers=admin_headers,
    )
    assert res.status_code == 200
    slots = res.json()
    assert isinstance(slots, list)
    assert len(slots) >= 2

    # Verificar slot regular na segunda-feira
    slot_segunda = next((s for s in slots if s.get("grade_id") == str(slot_fixo.id)), None)
    assert slot_segunda is not None
    assert slot_segunda["dia_semana"] == "Segunda"
    assert slot_segunda["horario_inicio"] == "08:00"
    assert slot_segunda["disciplina_nome"] == disc.nome
    assert slot_segunda["turma_id"] == str(sample_turma.id)

    # Verificar evento na terça-feira
    slot_evento = next((s for s in slots if s.get("agendamento_id") == str(evento.id)), None)
    assert slot_evento is not None
    assert slot_evento["tipo_slot"] == "EVENTO"
    assert slot_evento["titulo"] == "Encontro Pedagógico SEDUC"
    assert slot_evento["nome_evento"] == "Seminário Estadual"
    assert slot_evento["departamento"] == "UETEV"
    assert slot_evento["chamado"] == "CH-9876"

    # 5. Testar endpoint alternativo /api/v1/configuracoes/estudios/{id}/grade
    res_cfg = client.get(
        f"/api/v1/configuracoes/estudios/{estudio.id}/grade?data_inicio={segunda}&data_fim={domingo}",
        headers=admin_headers,
    )
    assert res_cfg.status_code == 200
    slots_cfg = res_cfg.json()
    assert len(slots_cfg) == len(slots)


def test_grade_estudio_inexistente(client, admin_headers):
    res = client.get(
        "/api/v1/turmas/grade-estudio/999999?data_inicio=2026-10-19&data_fim=2026-10-25",
        headers=admin_headers,
    )
    assert res.status_code == 200
    assert res.json() == []
