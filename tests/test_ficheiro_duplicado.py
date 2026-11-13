"""
Impede dois registros FINALIZADOS com o mesmo ficheiro na mesma data.
Rascunhos podem ser editados livremente; o bloqueio ocorre na finalização.
"""

from datetime import date

from fastapi import HTTPException
import pytest

from app.api.rotas_report import criar_relatorio, editar_relatorio, finalizar_relatorio
from app.schemas.class_report import ClassReportCreate


def _body_gravacao(turma_id, disc_id, prof_id, data_aula, horario, conteudo, estudio="Estúdio 01"):
    return {
        "data_aula": data_aula,
        "turno": "Manhã",
        "estudio": estudio,
        "turma_id": turma_id,
        "disciplina_id": disc_id,
        "professor_id": prof_id,
        "horario_aula": horario,
        "regular": "Sim",
        "tipo_aula": "Gravação estúdio",
        "canal_utilizado": "1",
        "conteudo_ministrado": conteudo,
        "bncc_habilidades": "Nenhuma",
        "youtube_link": "https://youtube.com/watch?v=abc",
        "tipo_recursos_utilizados": ["Quadro"],
    }


def test_gravacao_mesmo_ficheiro_mesma_data_e_bloqueada_na_finalizacao(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    dia = date(2026, 6, 15)

    primeiro = criar_relatorio(
        data=ClassReportCreate(
            **_body_gravacao(
                sample_turma.id, disc.id, prof.id, dia, "GRAVAÇÃO", "Introdução à óptica"
            )
        ),
        db=db_session,
        current_user=admin_user,
    )
    finalizar_relatorio(report_id=primeiro.id, db=db_session, current_user=admin_user)

    segundo = criar_relatorio(
        data=ClassReportCreate(
            **_body_gravacao(
                sample_turma.id,
                disc.id,
                prof.id,
                dia,
                "07:30 às 08:30",
                "Revisão de lentes P1",
            )
        ),
        db=db_session,
        current_user=admin_user,
    )

    with pytest.raises(HTTPException) as excinfo:
        editar_relatorio(
            report_id=segundo.id,
            data=ClassReportCreate(
                **_body_gravacao(
                    sample_turma.id,
                    disc.id,
                    prof.id,
                    dia,
                    "07:30 às 08:30",
                    "Introdução à óptica",
                )
            ),
            db=db_session,
            current_user=admin_user,
        )

    assert excinfo.value.status_code == 409
    assert "mesmo ficheiro" in str(excinfo.value.detail).lower()


def test_rascunho_pode_ser_editado_e_finalizado_sem_colidir_consigo(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    dia = date(2026, 6, 15)

    rascunho = criar_relatorio(
        data=ClassReportCreate(
            **_body_gravacao(
                sample_turma.id, disc.id, prof.id, dia, "GRAVAÇÃO", "Introdução à óptica"
            )
        ),
        db=db_session,
        current_user=admin_user,
    )

    editado = editar_relatorio(
        report_id=rascunho.id,
        data=ClassReportCreate(
            **_body_gravacao(
                sample_turma.id, disc.id, prof.id, dia, "GRAVAÇÃO", "Introdução à óptica"
            )
        ),
        db=db_session,
        current_user=admin_user,
    )
    assert editado.status == "RASCUNHO"

    finalizado = finalizar_relatorio(
        report_id=rascunho.id, db=db_session, current_user=admin_user
    )
    assert finalizado.status == "AGUARDANDO_VALIDACAO"  # v4: fila de validação (desde v3.1)


def test_mesmo_ficheiro_em_data_diferente_e_permitido(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]

    criar_relatorio(
        data=ClassReportCreate(
            **_body_gravacao(
                sample_turma.id, disc.id, prof.id, date(2026, 6, 15), "GRAVAÇÃO", "Introdução à óptica"
            )
        ),
        db=db_session,
        current_user=admin_user,
    )

    segundo = criar_relatorio(
        data=ClassReportCreate(
            **_body_gravacao(
                sample_turma.id, disc.id, prof.id, date(2026, 6, 16), "GRAVAÇÃO", "Introdução à óptica"
            )
        ),
        db=db_session,
        current_user=admin_user,
    )
    assert segundo.status == "RASCUNHO"


def test_mesmo_slot_conteudo_diferente_e_bloqueado(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    dia = date(2026, 6, 15)

    criar_relatorio(
        data=ClassReportCreate(
            **_body_gravacao(
                sample_turma.id, disc.id, prof.id, dia, "GRAVAÇÃO", "Introdução à óptica"
            )
        ),
        db=db_session,
        current_user=admin_user,
    )

    with pytest.raises(HTTPException) as excinfo:
        criar_relatorio(
            data=ClassReportCreate(
                **_body_gravacao(
                    sample_turma.id, disc.id, prof.id, dia, "GRAVAÇÃO", "Revisão de lentes P1"
                )
            ),
            db=db_session,
            current_user=admin_user,
        )
    assert excinfo.value.status_code == 409
    assert "slot operacional" in str(excinfo.value.detail).lower()


def test_editar_rascunho_para_ficheiro_ja_finalizado_e_bloqueado(
    admin_user, db_session, sample_turma, sample_professor_disciplina
):
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    dia = date(2026, 6, 15)

    primeiro = criar_relatorio(
        data=ClassReportCreate(
            **_body_gravacao(
                sample_turma.id, disc.id, prof.id, dia, "GRAVAÇÃO", "Introdução à óptica"
            )
        ),
        db=db_session,
        current_user=admin_user,
    )
    outro = criar_relatorio(
        data=ClassReportCreate(
            **_body_gravacao(
                sample_turma.id, disc.id, prof.id, dia, "07:30 às 08:30", "Revisão de lentes P1"
            )
        ),
        db=db_session,
        current_user=admin_user,
    )
    finalizar_relatorio(report_id=primeiro.id, db=db_session, current_user=admin_user)

    with pytest.raises(HTTPException) as excinfo:
        editar_relatorio(
            report_id=outro.id,
            data=ClassReportCreate(
                **_body_gravacao(
                    sample_turma.id, disc.id, prof.id, dia, "07:30 às 08:30", "Introdução à óptica"
                )
            ),
            db=db_session,
            current_user=admin_user,
        )

    assert excinfo.value.status_code == 409
    assert "mesmo ficheiro" in str(excinfo.value.detail).lower()
