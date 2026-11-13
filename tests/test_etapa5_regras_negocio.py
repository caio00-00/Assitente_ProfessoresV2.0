"""
Testes automatizados da Etapa 5:
- Demanda 1.1: Caso 1 (Antecipação de Aula & Chamado SEDUC)
- Demanda 1.2: Caso 2 (Mês de Execução × Mês de Referência & Reposição)
- Trava de Consistência Obrigatória de Faturamento (Assistente ↔ Diretor de Imagem)
"""

import pytest
from datetime import date, time
from uuid import uuid4

from app.models.class_report import ClassReport
from app.models.image_director_report import ImageDirectorReport, ImageDirectorLesson
from app.models.diretor_imagem import DiretorImagem
from app.models.auxiliares import Disciplina, Professor
from app.models.user import User


def test_antecipacao_seduc_chamado_nao_e_mais_cobrado_do_assistente(client, admin_headers, sample_turma, sample_professor_disciplina):
    """
    Reunião (out/2026): quem informa se é pedido da SEDUC (e o nº do chamado) é o diretor-chefe,
    na Agenda. O relatório do assistente não trava mais por falta do chamado.
    """
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]

    # 1. Sem chamado: o relatório é salvo (o chamado fica no agendamento da Agenda)
    payload_invalido = {
        "turma_id": str(sample_turma.id),
        "disciplina_id": str(disc.id),
        "professor_id": str(prof.id),
        "data_aula": "2026-10-15",
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "horario_aula": "07:30 - 08:30",
        "regular": "Sim",
        "tipo_aula": "Gravação estúdio",
        "conteudo_ministrado": "Aula de Antecipacao",
        "bncc_habilidades": "EM13MAT101",
        "tipo_recursos_utilizados": ["Slides"],
        "canal_utilizado": "1",
        "youtube_link": "https://youtube.com/watch?v=teste-seduc-sem-chamado",
        "solicitante_antecipacao": "SEDUC",
        "ticket_number": None,
    }
    res = client.post("/api/v1/reports/", json=payload_invalido, headers=admin_headers)
    assert res.status_code == 201, res.text

    # 2. Com chamado preenchido -> Sucesso 201
    payload_valido = dict(payload_invalido)
    payload_valido["data_aula"] = "2026-10-14"
    payload_valido["youtube_link"] = "https://youtube.com/watch?v=teste-seduc-com-chamado"
    payload_valido["ticket_number"] = "18097"
    res_ok = client.post("/api/v1/reports/", json=payload_valido, headers=admin_headers)
    assert res_ok.status_code == 201, res_ok.text
    assert res_ok.json()["ticket_number"] == "18097"
    assert res_ok.json()["solicitante_antecipacao"] == "SEDUC"


def test_antecipacao_professor_permite_sem_chamado(client, admin_headers, sample_turma, sample_professor_disciplina):
    """Demanda 1.1: Se solicitante_antecipacao == 'PROFESSOR', chamado é opcional (cobra 1x)."""
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]

    payload = {
        "turma_id": str(sample_turma.id),
        "disciplina_id": str(disc.id),
        "professor_id": str(prof.id),
        "data_aula": "2026-10-16",
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "horario_aula": "07:30 - 08:30",
        "regular": "Sim",
        "tipo_aula": "Gravação estúdio",
        "conteudo_ministrado": "Aula de Antecipacao Prof",
        "bncc_habilidades": "EM13MAT102",
        "tipo_recursos_utilizados": ["Slides"],
        "canal_utilizado": "1",
        "youtube_link": "https://youtube.com/watch?v=teste-prof-sem-chamado",
        "solicitante_antecipacao": "PROFESSOR",
        "ticket_number": None,
    }
    res = client.post("/api/v1/reports/", json=payload, headers=admin_headers)
    assert res.status_code == 201, res.text
    assert res.json()["solicitante_antecipacao"] == "PROFESSOR"


def test_mes_execucao_e_referencia_com_indicativo_reposicao(client, admin_headers, sample_turma, sample_professor_disciplina):
    """Demanda 1.2 & Item 9: Separação de data_execucao_real e data_referencia_aula com indicativo automático."""
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]

    payload = {
        "turma_id": str(sample_turma.id),
        "disciplina_id": str(disc.id),
        "professor_id": str(prof.id),
        "data_aula": "2026-10-05",  # Mês de Execução (outubro)
        "turno": "Manhã",
        "estudio": "Estúdio 01",
        "horario_aula": "07:30 - 08:30",
        "regular": "Sim",
        "tipo_aula": "Gravação estúdio",
        "conteudo_ministrado": "Reposicao de Falta",
        "bncc_habilidades": "EM13MAT103",
        "tipo_recursos_utilizados": ["Slides"],
        "canal_utilizado": "1",
        "youtube_link": "https://youtube.com/watch?v=teste-reposicao",
        "data_execucao_real": "2026-10-05",
        "data_referencia_aula": "2026-09-25",  # Mês de Referência (setembro)
    }
    res = client.post("/api/v1/reports/", json=payload, headers=admin_headers)
    assert res.status_code == 201, res.text
    dados = res.json()
    assert dados["data_referencia_aula"] == "2026-09-25"
    assert dados["data_execucao_real"] == "2026-10-05"
    assert "reposição/falta" in dados["motivo_referencia"]
    assert "25/09/2026" in dados["motivo_referencia"]


def test_trava_consistencia_divergencia_bloqueia_finalizacao(client, admin_headers, db_session, sample_turma, sample_professor_disciplina):
    """
    Demanda 1.1 e 138: Trava de consistência de faturamento.
    Se o Diretor de Imagem registrou Transmissão e o Assistente tenta finalizar como Gravação,
    a finalização deve ser barrada com erro 422.
    """
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    dir_img = DiretorImagem(nome="Diretor Consistência 1", is_active=True)
    db_session.add(dir_img)
    db_session.commit()
    db_session.refresh(dir_img)

    # 1. Cria e finaliza relatório do Diretor de Imagem com aula em "Transmissão"
    res_idr = client.post(
        "/api/v1/image-director/",
        json={
            "diretor_imagem_id": str(dir_img.id),
            "data_relatorio": "2026-10-17",
            "turno": "Manhã",
            "estudio": "Estúdio 01",
            "turma_id": str(sample_turma.id),
            "disciplina_id": str(disc.id),
            "professor_id": str(prof.id),
            "horario_aula": "07:30 - 08:30",
            "origem": "grade",
            "youtube_link": "https://youtube.com/watch?v=transmissao-idr",
        },
        headers=admin_headers,
    )
    assert res_idr.status_code == 201, res_idr.text
    idr_id = res_idr.json()["id"]

    res_lesson = client.post(
        f"/api/v1/image-director/{idr_id}/lessons",
        json={
            "disciplina_nome": disc.nome,
            "professor_nome": prof.nome,
            "transmissao_ou_gravada": "Transmissão",
            "canal_utilizado": "1",
        },
        headers=admin_headers,
    )
    assert res_lesson.status_code == 201, res_lesson.text

    res_fin_idr = client.post(
        f"/api/v1/image-director/{idr_id}/finalize",
        json={"youtube_link": "https://youtube.com/watch?v=transmissao-idr"},
        headers=admin_headers,
    )
    assert res_fin_idr.status_code == 200, res_fin_idr.text

    # 2. Cria o relatório do Assistente como "Gravação estúdio" (divergência!)
    res_cr = client.post(
        "/api/v1/reports/",
        json={
            "turma_id": str(sample_turma.id),
            "disciplina_id": str(disc.id),
            "professor_id": str(prof.id),
            "diretor_imagem_id": str(dir_img.id),
            "data_aula": "2026-10-17",
            "turno": "Manhã",
            "estudio": "Estúdio 01",
            "horario_aula": "07:30 - 08:30",
            "regular": "Sim",
            "tipo_aula": "Gravação estúdio",  # Gravação vs Transmissão no IDR!
            "conteudo_ministrado": "Aula Gravada Divergente",
            "bncc_habilidades": "EM13MAT104",
            "tipo_recursos_utilizados": ["Slides"],
            "canal_utilizado": "1",
            "youtube_link": "https://youtube.com/watch?v=transmissao-idr",
        },
        headers=admin_headers,
    )
    assert res_cr.status_code == 201, res_cr.text
    cr_id = res_cr.json()["id"]

    # 3. Tentar finalizar o relatório do Assistente -> DEVE falhar com 422
    res_fin_cr = client.post(f"/api/v1/reports/{cr_id}/finalize", json={}, headers=admin_headers)
    assert res_fin_cr.status_code == 422, res_fin_cr.text
    assert "Inconsistência de faturamento" in res_fin_cr.json()["detail"]


def test_trava_consistencia_ambos_gravacao_sucesso(client, admin_headers, db_session, sample_turma, sample_professor_disciplina):
    """
    Demanda 1.1 e 138: Quando ambos os relatórios são Gravação (ou ambos Transmissão),
    a finalização deve ocorrer com sucesso.
    """
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    dir_img = DiretorImagem(nome="Diretor Consistência 2", is_active=True)
    db_session.add(dir_img)
    db_session.commit()
    db_session.refresh(dir_img)

    # 1. Cria relatório do Diretor de Imagem com aula em "Aula gravada"
    res_idr = client.post(
        "/api/v1/image-director/",
        json={
            "diretor_imagem_id": str(dir_img.id),
            "data_relatorio": "2026-10-18",
            "turno": "Manhã",
            "estudio": "Estúdio 02",
            "turma_id": str(sample_turma.id),
            "disciplina_id": str(disc.id),
            "professor_id": str(prof.id),
            "horario_aula": "07:30 - 08:30",
            "origem": "grade",
            "youtube_link": "https://youtube.com/watch?v=gravacao-idr",
        },
        headers=admin_headers,
    )
    assert res_idr.status_code == 201, res_idr.text
    idr_id = res_idr.json()["id"]

    client.post(
        f"/api/v1/image-director/{idr_id}/lessons",
        json={
            "disciplina_nome": disc.nome,
            "professor_nome": prof.nome,
            "transmissao_ou_gravada": "Aula gravada",
            "canal_utilizado": None,
        },
        headers=admin_headers,
    )

    # 2. Cria relatório do Assistente também como "Gravação estúdio"
    res_cr = client.post(
        "/api/v1/reports/",
        json={
            "turma_id": str(sample_turma.id),
            "disciplina_id": str(disc.id),
            "professor_id": str(prof.id),
            "diretor_imagem_id": str(dir_img.id),
            "data_aula": "2026-10-18",
            "turno": "Manhã",
            "estudio": "Estúdio 02",
            "horario_aula": "07:30 - 08:30",
            "regular": "Sim",
            "tipo_aula": "Gravação estúdio",
            "conteudo_ministrado": "Aula Gravada Consistente",
            "bncc_habilidades": "EM13MAT105",
            "tipo_recursos_utilizados": ["Slides"],
            "canal_utilizado": "1",
            "youtube_link": "https://youtube.com/watch?v=gravacao-idr",
        },
        headers=admin_headers,
    )
    assert res_cr.status_code == 201, res_cr.text
    cr_id = res_cr.json()["id"]

    # 3. Finalizar ambos -> Ambos devem passar com 200
    res_fin_idr = client.post(
        f"/api/v1/image-director/{idr_id}/finalize",
        json={"youtube_link": "https://youtube.com/watch?v=gravacao-idr"},
        headers=admin_headers,
    )
    assert res_fin_idr.status_code == 200, res_fin_idr.text

    res_fin_cr = client.post(f"/api/v1/reports/{cr_id}/finalize", json={}, headers=admin_headers)
    assert res_fin_cr.status_code == 200, res_fin_cr.text
    assert res_fin_cr.json()["status"] == "AGUARDANDO_VALIDACAO"
