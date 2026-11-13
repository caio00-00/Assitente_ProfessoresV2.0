"""
AP-006 — Reprocessamento na edição apenas quando a NOMENCLATURA muda.

Regra (decisão de produto 30/06): ao editar um relatório FINALIZADO, só
recalcular nome_ficheiro_gerado, limpar links e resetar compliance para
Pendente quando um campo que afeta o nome do arquivo mudar
(disciplina/conteúdo/data/turma). Editar um campo irrelevante (ex.:
youtube_link) NÃO deve descartar os links já vinculados nem zerar o
compliance.
"""

from datetime import date, time

from app.models.auxiliares import Grade
from app.api.rotas_report import (
    criar_relatorio,
    finalizar_relatorio,
    editar_relatorio,
)
from app.schemas.class_report import ClassReportCreate


def _setup_slot_and_report(db_session, admin_user, turma, prof, disc):
    grade_slot = Grade(
        turma_id=turma.id,
        disciplina_id=disc.id,
        dia_semana=0,  # segunda
        horario_inicio=time(7, 30),
        horario_fim=time(8, 30),
        turno_aula="MANHÃ",
        canal_iptv=1,
        versao="Grade Base",
    )
    db_session.add(grade_slot)
    db_session.commit()

    body = {
        "data_aula": date(2026, 6, 8),  # segunda-feira
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "turma_id": turma.id,
        "disciplina_id": disc.id,
        "professor_id": prof.id,
        "horario_aula": "07:30 às 08:30",
        "regular": "Sim",
        "tipo_aula": "Transmissão ao vivo",
        "canal_utilizado": "1",
        "conteudo_ministrado": "Aula 1",
        "bncc_habilidades": "Nenhuma",
        "youtube_link": "http://youtube.com/watch?v=orig",
        "tipo_recursos_utilizados": ["Quadro"],
    }
    report = criar_relatorio(data=ClassReportCreate(**body), db=db_session, current_user=admin_user)
    report = finalizar_relatorio(report_id=report.id, db=db_session, current_user=admin_user)
    assert report.status == "AGUARDANDO_VALIDACAO"  # v4: fila de validação (desde v3.1)

    # Simula vínculos já preenchidos pela integração/compliance
    report.video_link = "http://drive/video"
    report.slide_link = "http://drive/slide"
    report.md5_checksum = "abc123"
    report.status_compliance = "Verde"
    db_session.add(report)
    db_session.commit()
    return report, body


def test_edicao_sem_mudar_nomenclatura_preserva_links(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    report, body = _setup_slot_and_report(db_session, admin_user, sample_turma, prof, disc)
    nome_antes = report.nome_ficheiro_gerado

    # Edita só um campo que NÃO afeta a nomenclatura.
    # slide_link é campo editável do payload (o frontend o ecoa de volta).
    body_edit = body.copy()
    body_edit["youtube_link"] = "http://youtube.com/watch?v=NOVO"
    body_edit["slide_link"] = "http://drive/slide"
    editado = editar_relatorio(
        report_id=report.id, data=ClassReportCreate(**body_edit),
        db=db_session, current_user=admin_user,
    )

    assert editado.nome_ficheiro_gerado == nome_antes
    # video_link/status_compliance/md5 são geridos pelo compliance (fora do
    # payload) → preservados quando a nomenclatura não muda.
    assert editado.video_link == "http://drive/video"      # preservado
    assert editado.md5_checksum == "abc123"                # preservado
    assert editado.status_compliance == "Verde"            # NÃO resetado
    assert editado.slide_link == "http://drive/slide"      # veio no payload, mantido


def test_edicao_mudando_conteudo_reprocessa(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    report, body = _setup_slot_and_report(db_session, admin_user, sample_turma, prof, disc)
    nome_antes = report.nome_ficheiro_gerado

    # Edita o conteúdo → muda o nome do arquivo → deve reprocessar.
    # Mesmo enviando slide_link no payload, o reprocesso o limpa para forçar
    # nova busca no Drive sob o novo nome.
    body_edit = body.copy()
    body_edit["conteudo_ministrado"] = "Aula 1 CONTEUDO NOVO"
    body_edit["slide_link"] = "http://drive/slide"
    editado = editar_relatorio(
        report_id=report.id, data=ClassReportCreate(**body_edit),
        db=db_session, current_user=admin_user,
    )

    assert editado.nome_ficheiro_gerado != nome_antes
    assert editado.video_link is None
    assert editado.slide_link is None
    assert editado.md5_checksum is None
    assert editado.status_compliance == "Pendente"
