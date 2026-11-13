"""Reunião: na Grade Horária por turma, assistente e diretores não incluem nem excluem horário."""
from datetime import time
from uuid import uuid4

from app.core.security import create_access_token, get_password_hash
from app.models.auxiliares import Disciplina, Grade
from app.models.infraestrutura import Estudio
from app.models.user import User


def _headers(db, role):
    u = User(email=f"{role}-{uuid4().hex[:6]}@t.com", full_name=role, role=role,
             hashed_password=get_password_hash("x"), is_active=True, email_confirmed=True)
    db.add(u)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(data={'sub': u.email, 'role': u.role, 'user_id': str(u.id)})}"}


def test_so_coordenacao_inclui_e_exclui_horario(client, db_session, sample_turma):
    est = Estudio(nome="Estúdio 01", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    disc = Disciplina(nome="FÍSICA")
    db_session.add_all([est, disc])
    db_session.commit()
    grade = Grade(turma_id=sample_turma.id, disciplina_id=disc.id, estudio_id=est.id,
                  dia_semana=2, horario_inicio=time(7, 30), horario_fim=time(8, 30))
    db_session.add(grade)
    db_session.commit()
    corpo = {"disciplina_id": str(disc.id), "dia_semana": 3, "horario_inicio": "07:30",
             "horario_fim": "08:30", "estudio_id": est.id}
    for role in ("assistente", "diretor_imagem", "diretor_chefe"):
        h = _headers(db_session, role)
        assert client.post(f"/api/v1/turmas/{sample_turma.id}/grade", json=corpo, headers=h).status_code == 403
        assert client.delete(f"/api/v1/turmas/grade/{grade.id}", headers=h).status_code == 403
    h = _headers(db_session, "coordenador")
    assert client.post(f"/api/v1/turmas/{sample_turma.id}/grade", json=corpo, headers=h).status_code == 201
    assert client.delete(f"/api/v1/turmas/grade/{grade.id}", headers=h).status_code == 204
