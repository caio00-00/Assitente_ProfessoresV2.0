"""
Canal Educação v3.0 — Tests: Duplicity and Slot Matching
Tests for slot-based duplicate reports prevention and two-pass matching on Grade Horária.
"""

from datetime import date, time
from app.models.auxiliares import Grade, Disciplina, Professor, ProfessorDisciplina
from app.models.class_report import ClassReport
from app.api.rotas_report import criar_relatorio, editar_relatorio, finalizar_relatorio
from app.api.rotas_turma import listar_grade_turma
from app.schemas.class_report import ClassReportCreate
from fastapi import HTTPException
import pytest


def test_duplicate_reports_blocked_and_two_pass_match(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]

    # 1. Crie um segundo professor e disciplina para poder testar conflitos e trocas
    prof2 = Professor(nome="Maria Souza")
    disc2 = Disciplina(nome="FÍSICA", nomenclatura_padrao="FIS")
    db_session.add(prof2)
    db_session.add(disc2)
    db_session.flush()
    link2 = ProfessorDisciplina(professor_id=prof2.id, disciplina_id=disc2.id)
    db_session.add(link2)
    db_session.commit()

    # 2. Configure 1 slot oficial na grade para a turma
    # Dia 0 = Segunda-feira (weekday() = 0)
    data_segunda = date(2026, 6, 8)  # Segunda-feira
    assert data_segunda.weekday() == 0

    grade_slot = Grade(
        turma_id=sample_turma.id,
        disciplina_id=disc.id,
        dia_semana=0,
        horario_inicio=time(7, 30),
        horario_fim=time(8, 30),
        turno_aula="MANHÃ",
        canal_iptv=1,
        versao="Grade Base",
    )
    db_session.add(grade_slot)
    db_session.commit()

    # 3. Criar primeiro relatório (RASCUNHO) para o slot
    body1 = {
        "data_aula": date(2026, 6, 8),
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "turma_id": sample_turma.id,
        "disciplina_id": disc.id,
        "professor_id": prof.id,
        "horario_aula": "07:30 às 08:30",
        "regular": "Sim",
        "tipo_aula": "Transmissão ao vivo",
        "canal_utilizado": "1",
        "conteudo_ministrado": "Aula 1",
        "bncc_habilidades": "Nenhuma",
        "youtube_link": "link",
        "tipo_recursos_utilizados": ["Quadro"],
    }
    data1 = ClassReportCreate(**body1)
    report1 = criar_relatorio(data=data1, db=db_session, current_user=admin_user)
    assert report1.status == "RASCUNHO"
    report1_id = report1.id

    # 4. Tentar criar um segundo relatório para o mesmo slot (deve ser bloqueado informando status RASCUNHO)
    body2 = {
        "data_aula": date(2026, 6, 8),
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "turma_id": sample_turma.id,
        "disciplina_id": disc.id,
        "professor_id": prof.id,
        "horario_aula": "07:30 às 08:30",
        "regular": "Sim",
        "tipo_aula": "Transmissão ao vivo",
        "canal_utilizado": "1",
        "conteudo_ministrado": "Aula 1 duplicada",
        "bncc_habilidades": "Nenhuma",
        "youtube_link": "link",
        "tipo_recursos_utilizados": ["Quadro"],
    }
    data2 = ClassReportCreate(**body2)
    with pytest.raises(HTTPException) as excinfo:
        criar_relatorio(data=data2, db=db_session, current_user=admin_user)
    assert excinfo.value.status_code == 409
    assert (
        "RASCUNHO" in str(excinfo.value.detail)
        or "choque de horário" in str(excinfo.value.detail).lower()
    )

    # 5. Tentar criar para o mesmo slot mas outra disciplina (deve ser bloqueado também porque há apenas 1 slot configurado)
    body3 = {
        "data_aula": date(2026, 6, 8),
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "turma_id": sample_turma.id,
        "disciplina_id": disc2.id,
        "professor_id": prof2.id,
        "horario_aula": "07:30 às 08:30",
        "regular": "Sim",
        "tipo_aula": "Transmissão ao vivo",
        "canal_utilizado": "1",
        "conteudo_ministrado": "Aula Física no mesmo slot",
        "bncc_habilidades": "Nenhuma",
        "youtube_link": "link",
        "tipo_recursos_utilizados": ["Quadro"],
    }
    data3 = ClassReportCreate(**body3)
    with pytest.raises(HTTPException) as excinfo:
        criar_relatorio(data=data3, db=db_session, current_user=admin_user)
    assert excinfo.value.status_code == 400
    assert (
        "RASCUNHO" in str(excinfo.value.detail)
        or "choque de horário" in str(excinfo.value.detail).lower()
    )

    # 6. Atualizar o relatório original deve ser permitido (não pode colidir consigo mesmo)
    body1_edit = body1.copy()
    body1_edit["conteudo_ministrado"] = "Aula 1 editada"
    data1_edit = ClassReportCreate(**body1_edit)
    report_edit = editar_relatorio(report_id=report1_id, data=data1_edit, db=db_session, current_user=admin_user)
    assert report_edit.status == "RASCUNHO"
    assert report_edit.conteudo_ministrado == "AULA 1 EDITADA"

    # 7. Testar correspondência (match) no endpoint /grade
    grade_data = listar_grade_turma(
        turma_id=sample_turma.id,
        data_consulta="2026-06-08",
        db=db_session,
        current_user=admin_user,
    )
    assert len(grade_data) == 1
    assert grade_data[0]["report_id"] == str(report1_id)
    assert grade_data[0]["report_status"] == "RASCUNHO"

    # 8. Alterar disciplina do relatório original (e.g. substituição)
    body1_sub = body1.copy()
    body1_sub["disciplina_id"] = disc2.id
    body1_sub["professor_id"] = prof2.id
    body1_sub["conteudo_ministrado"] = "Aula Física de substituição"
    data1_sub = ClassReportCreate(**body1_sub)
    
    report_sub = editar_relatorio(report_id=report1_id, data=data1_sub, db=db_session, current_user=admin_user)
    assert report_sub.disciplina_id == disc2.id

    # 9. Testar correspondência (match) difusa no endpoint /grade (mesmo com disciplinas diferentes, deve associar pelo horário)
    grade_data_diff = listar_grade_turma(
        turma_id=sample_turma.id,
        data_consulta="2026-06-08",
        db=db_session,
        current_user=admin_user,
    )
    assert len(grade_data_diff) == 1
    assert grade_data_diff[0]["report_id"] == str(report1_id)
    assert grade_data_diff[0]["report_status"] == "RASCUNHO"


def test_tecnico_bypass_geminada_validation(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    # 1. Update the sample_turma modalidade to "TECNICO"
    sample_turma.modalidade = "TECNICO"
    db_session.add(sample_turma)
    db_session.flush()

    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]

    # 2. Configure two slots in the grade on Monday (Dia 0)
    # Dia 0 = Segunda-feira (weekday() = 0)
    data_segunda = date(2026, 6, 8)  # Segunda-feira
    assert data_segunda.weekday() == 0

    grade_slot1 = Grade(
        turma_id=sample_turma.id,
        disciplina_id=disc.id,
        dia_semana=0,
        horario_inicio=time(7, 30),
        horario_fim=time(8, 30),
        turno_aula="MANHÃ",
        canal_iptv=1,
        versao="Grade Base",
    )
    grade_slot2 = Grade(
        turma_id=sample_turma.id,
        disciplina_id=disc.id,
        dia_semana=0,
        horario_inicio=time(8, 30),
        horario_fim=time(9, 30),
        turno_aula="MANHÃ",
        canal_iptv=1,
        versao="Grade Base",
    )
    db_session.add(grade_slot1)
    db_session.add(grade_slot2)
    db_session.commit()

    # 3. Create the first report (to be finalized) - since it is TECNICO, name pattern requires AULA \d{2} prefix in conteudo_ministrado
    body1 = {
        "data_aula": date(2026, 6, 8),
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "turma_id": sample_turma.id,
        "disciplina_id": disc.id,
        "professor_id": prof.id,
        "horario_aula": "07:30 às 08:30",
        "regular": "Sim",
        "tipo_aula": "Transmissão ao vivo",
        "canal_utilizado": "1",
        "conteudo_ministrado": "AULA 01 Introdução",
        "bncc_habilidades": "Nenhuma",
        "youtube_link": "http://youtube.com/watch?v=123",
        "tipo_recursos_utilizados": ["Quadro"],
    }
    data1 = ClassReportCreate(**body1)
    report1 = criar_relatorio(data=data1, db=db_session, current_user=admin_user)
    
    # Finalize the first report
    report1_finalizado = finalizar_relatorio(report_id=report1.id, db=db_session, current_user=admin_user)
    assert report1_finalizado.status == "AGUARDANDO_VALIDACAO"  # v4: fila de validação (desde v3.1)

    # 4. Create the second report for the SAME turma/disciplina/data, but different slot (08:30 to 09:30)
    # Since it is TECNICO, it should NOT require P1/P2/P3. We will try to finalize it without any suffix.
    body2 = {
        "data_aula": date(2026, 6, 8),
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "turma_id": sample_turma.id,
        "disciplina_id": disc.id,
        "professor_id": prof.id,
        "horario_aula": "08:30 às 09:30",
        "regular": "Sim",
        "tipo_aula": "Transmissão ao vivo",
        "canal_utilizado": "1",
        "conteudo_ministrado": "AULA 02 Introdução", # No suffix P1/P2/P3 here!
        "bncc_habilidades": "Nenhuma",
        "youtube_link": "http://youtube.com/watch?v=456",
        "tipo_recursos_utilizados": ["Quadro"],
    }
    data2 = ClassReportCreate(**body2)
    report2 = criar_relatorio(data=data2, db=db_session, current_user=admin_user)

    # Finalizing report2 should succeed without throwing a geminada exception (normally, it would fail without P1/P2/P3)
    report2_finalizado = finalizar_relatorio(report_id=report2.id, db=db_session, current_user=admin_user)
    assert report2_finalizado.status == "AGUARDANDO_VALIDACAO"  # v4: fila de validação (desde v3.1)


def test_gravacao_estudio_nao_bloqueia_transmissao_no_mesmo_slot(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]

    data_segunda = date(2026, 6, 15)
    assert data_segunda.weekday() == 0

    grade_slot = Grade(
        turma_id=sample_turma.id,
        disciplina_id=disc.id,
        dia_semana=0,
        horario_inicio=time(7, 30),
        horario_fim=time(8, 30),
        turno_aula="MANHÃ",
        canal_iptv=1,
        versao="Grade Base",
    )
    db_session.add(grade_slot)
    db_session.commit()

    body_special = {
        "data_aula": date(2026, 6, 15),
        "turno": "Manhã",
        "estudio": "Estúdio 02",
        "turma_id": sample_turma.id,
        "disciplina_id": disc.id,
        "professor_id": prof.id,
        "horario_aula": "07:30 às 08:30",
        "regular": "Sim",
        "tipo_aula": "Gravação estúdio",
        "canal_utilizado": "2",
        "conteudo_ministrado": "Gravação Especial de Física",
        "bncc_habilidades": "Nenhuma",
        "youtube_link": "http://youtube.com/watch?v=spec",
        "tipo_recursos_utilizados": ["Quadro"],
    }
    report_spec = criar_relatorio(
        data=ClassReportCreate(**body_special), db=db_session, current_user=admin_user
    )
    finalizar_relatorio(report_id=report_spec.id, db=db_session, current_user=admin_user)

    body_regular = {
        **body_special,
        "estudio": "Estúdio 01",
        "tipo_aula": "Transmissão ao vivo",
        "canal_utilizado": "1",
        "conteudo_ministrado": "Aula regular de física P1",
        "youtube_link": "http://youtube.com/watch?v=reg",
    }
    report_regular = criar_relatorio(
        data=ClassReportCreate(**body_regular), db=db_session, current_user=admin_user
    )
    finalizado = finalizar_relatorio(
        report_id=report_regular.id, db=db_session, current_user=admin_user
    )
    assert finalizado.status == "AGUARDANDO_VALIDACAO"  # v4: fila de validação (desde v3.1)

    body_special2 = {
        **body_special,
        "estudio": "Estúdio 03",
        "tipo_aula": "Gravação externa",
        "canal_utilizado": "3",
        "conteudo_ministrado": "Outra gravação especial",
        "youtube_link": "http://youtube.com/watch?v=spec2",
    }
    with pytest.raises(HTTPException) as excinfo2:
        criar_relatorio(
            data=ClassReportCreate(**body_special2), db=db_session, current_user=admin_user
        )
    assert excinfo2.value.status_code == 409


def test_horario_variante_bloqueia_duplicata(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]

    body1 = {
        "data_aula": date(2026, 6, 8),
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "turma_id": sample_turma.id,
        "disciplina_id": disc.id,
        "professor_id": prof.id,
        "horario_aula": "07:30 às 08:30",
        "regular": "Sim",
        "tipo_aula": "Transmissão ao vivo",
        "canal_utilizado": "1",
        "conteudo_ministrado": "Aula 1",
        "bncc_habilidades": "Nenhuma",
        "youtube_link": "link",
        "tipo_recursos_utilizados": ["Quadro"],
    }
    criar_relatorio(data=ClassReportCreate(**body1), db=db_session, current_user=admin_user)

    body2 = {**body1, "horario_aula": "07:30 - 08:30", "conteudo_ministrado": "Aula 1 dup"}
    with pytest.raises(HTTPException) as excinfo:
        criar_relatorio(data=ClassReportCreate(**body2), db=db_session, current_user=admin_user)
    assert excinfo.value.status_code == 409


def test_rascunho_pode_ser_editado_e_finalizado_com_outro_rascunho_no_slot(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    """Outro RASCUNHO no mesmo slot não bloqueia salvar/finalizar o rascunho escolhido."""
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    data_aula = date(2026, 6, 8)

    body = {
        "data_aula": data_aula,
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "turma_id": sample_turma.id,
        "disciplina_id": disc.id,
        "professor_id": prof.id,
        "horario_aula": "1º Horário",
        "regular": "Sim",
        "tipo_aula": "Transmissão ao vivo",
        "canal_utilizado": "1",
        "conteudo_ministrado": "Aula principal",
        "bncc_habilidades": "Nenhuma",
        "youtube_link": "https://youtube.com/watch?v=abc",
        "tipo_recursos_utilizados": ["Quadro"],
    }
    principal = criar_relatorio(
        data=ClassReportCreate(**body), db=db_session, current_user=admin_user
    )

    # Simula rascunho órfão duplicado (ex.: POST sem report_id após reload)
    db_session.add(
        ClassReport(
            created_by=admin_user.id,
            data_aula=data_aula,
            turno="Manhã",
            estudio="Estúdio 02",
            turma_id=sample_turma.id,
            disciplina_id=disc.id,
            professor_id=prof.id,
            horario_aula="1º Horário",
            regular="Sim",
            tipo_aula="Transmissão ao vivo",
            canal_utilizado="1",
            conteudo_ministrado="RASCUNHO DUPLICADO",
            bncc_habilidades="Nenhuma",
            youtube_link="https://youtube.com/watch?v=xyz",
            tipo_recursos_utilizados=["Quadro"],
            status="RASCUNHO",
        )
    )
    db_session.commit()

    editado = editar_relatorio(
        report_id=principal.id,
        data=ClassReportCreate(**body),
        db=db_session,
        current_user=admin_user,
    )
    assert editado.status == "RASCUNHO"

    finalizado = finalizar_relatorio(
        report_id=principal.id, db=db_session, current_user=admin_user
    )
    assert finalizado.status == "AGUARDANDO_VALIDACAO"  # v4: fila de validação (desde v3.1)


def test_finalizar_rascunho_ignora_choque_com_outro_rascunho(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    """Choque de horário na finalização considera só registros FINALIZADOS."""
    from datetime import time

    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    data_aula = date(2026, 8, 18)

    body = {
        "data_aula": data_aula,
        "turno": "Tarde",
        "estudio": "Estúdio 4",
        "turma_id": sample_turma.id,
        "disciplina_id": disc.id,
        "professor_id": prof.id,
        "horario_aula": "1º Horário",
        "regular": "Sim",
        "tipo_aula": "Transmissão ao vivo",
        "canal_utilizado": "4",
        "conteudo_ministrado": "Equações do 2 grau",
        "bncc_habilidades": "Nenhuma",
        "youtube_link": "https://youtube.com/watch?v=abc",
        "tipo_recursos_utilizados": ["Quadro"],
    }
    principal = criar_relatorio(
        data=ClassReportCreate(**body), db=db_session, current_user=admin_user
    )

    db_session.add(
        ClassReport(
            created_by=admin_user.id,
            data_aula=data_aula,
            turno="Tarde",
            estudio="Estúdio 4",
            turma_id=sample_turma.id,
            disciplina_id=disc.id,
            professor_id=prof.id,
            horario_aula="1º Horário",
            regular="Sim",
            tipo_aula="Transmissão ao vivo",
            canal_utilizado="4",
            conteudo_ministrado="RASCUNHO DUPLICADO",
            bncc_habilidades="Nenhuma",
            youtube_link="https://youtube.com/watch?v=xyz",
            tipo_recursos_utilizados=["Quadro"],
            status="RASCUNHO",
            start_time=time(13, 0),
            end_time=time(14, 0),
        )
    )
    db_session.commit()

    finalizado = finalizar_relatorio(
        report_id=principal.id, db=db_session, current_user=admin_user
    )
    assert finalizado.status == "AGUARDANDO_VALIDACAO"  # v4: fila de validação (desde v3.1)


def test_editar_finalizado_ignora_rascunho_orfao_no_slot(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    """Relatório FINALIZADO pode ser editado mesmo com rascunho órfão no mesmo slot."""
    from datetime import time

    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    data_aula = date(2026, 8, 18)

    body = {
        "data_aula": data_aula,
        "turno": "Tarde",
        "estudio": "Estúdio 4",
        "turma_id": sample_turma.id,
        "disciplina_id": disc.id,
        "professor_id": prof.id,
        "horario_aula": "1º Horário",
        "regular": "Sim",
        "tipo_aula": "Transmissão ao vivo",
        "canal_utilizado": "4",
        "conteudo_ministrado": "Equações do 2 grau",
        "bncc_habilidades": "Nenhuma",
        "youtube_link": "https://youtube.com/watch?v=abc",
        "tipo_recursos_utilizados": ["Quadro"],
    }
    principal = criar_relatorio(
        data=ClassReportCreate(**body), db=db_session, current_user=admin_user
    )
    finalizar_relatorio(report_id=principal.id, db=db_session, current_user=admin_user)

    db_session.add(
        ClassReport(
            created_by=admin_user.id,
            data_aula=data_aula,
            turno="Tarde",
            estudio="Estúdio 4",
            turma_id=sample_turma.id,
            disciplina_id=disc.id,
            professor_id=prof.id,
            horario_aula="1º Horário",
            regular="Sim",
            tipo_aula="Transmissão ao vivo",
            canal_utilizado="4",
            conteudo_ministrado="RASCUNHO ORFAO",
            bncc_habilidades="Nenhuma",
            youtube_link="https://youtube.com/watch?v=xyz",
            tipo_recursos_utilizados=["Quadro"],
            status="RASCUNHO",
            start_time=time(13, 0),
            end_time=time(14, 0),
        )
    )
    db_session.commit()

    body_edit = body.copy()
    body_edit["youtube_link"] = "https://youtube.com/watch?v=editado"
    editado = editar_relatorio(
        report_id=principal.id,
        data=ClassReportCreate(**body_edit),
        db=db_session,
        current_user=admin_user,
    )
    assert editado.status == "AGUARDANDO_VALIDACAO"  # v4: fila de validação (desde v3.1)
    assert editado.youtube_link == "https://youtube.com/watch?v=editado"
