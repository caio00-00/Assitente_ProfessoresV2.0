"""Auditoria: pendências operacionais vs slots sem professor vinculado."""

from datetime import date, time

from app.models.auxiliares import Disciplina, Grade


def test_audit_separa_pendentes_operacionais_e_sem_professor(
    client, admin_headers, db_session, sample_turma, sample_professor_disciplina
):
    disc_com = sample_professor_disciplina["disciplina"]

    disc_sem = Disciplina(nome="FILOSOFIA", nomenclatura_padrao="FIL")
    db_session.add(disc_sem)
    db_session.flush()

    db_session.add(
        Grade(
            turma_id=sample_turma.id,
            disciplina_id=disc_com.id,
            dia_semana=0,
            horario_inicio=time(7, 30),
            horario_fim=time(8, 30),
            turno_aula="MANHÃ",
            canal_iptv=1,
            versao="Grade Base",
        )
    )
    db_session.add(
        Grade(
            turma_id=sample_turma.id,
            disciplina_id=disc_sem.id,
            dia_semana=0,
            horario_inicio=time(9, 0),
            horario_fim=time(10, 0),
            turno_aula="MANHÃ",
            canal_iptv=2,
            versao="Grade Base",
        )
    )
    db_session.commit()

    res = client.get(
        "/api/v1/reports/audit-stats",
        params={
            "data_inicio": "2026-06-08",
            "data_fim": "2026-06-08",
            "turma_id": str(sample_turma.id),
        },
        headers=admin_headers,
    )
    assert res.status_code == 200
    result = res.json()

    assert result["pendentes_operacionais"] == 1
    assert result["pendentes_sem_professor"] == 1
    assert result["previstos_pendentes"] == 1
    assert len(result["pendentes_detalhes"]) == 1
    assert len(result["sem_professor_detalhes"]) == 1
    assert result["pendentes_detalhes"][0]["tem_professor_associado"] is True
    assert result["sem_professor_detalhes"][0]["tem_professor_associado"] is False
    assert "João" in result["pendentes_detalhes"][0]["professor_nome"]
