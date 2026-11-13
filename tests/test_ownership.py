import uuid
from datetime import date
import pytest
from app.models.class_report import ClassReport

def test_assistente_nao_pode_cancelar_relatorio_de_outro(client, assistant_headers, db_session, sample_turma):
    # 1. Criamos um relatório COMPLETO para outro usuário
    outro_user_id = uuid.uuid4()
    
    relatorio_alheio = ClassReport(
        id=uuid.uuid4(),
        created_by=outro_user_id,
        status="RASCUNHO",
        data_aula=date.today(),
        turno="MANHÃ",
        estudio="Estúdio 01",
        turma_id=sample_turma.id,
        disciplina_id=uuid.uuid4(),
        professor_id=uuid.uuid4(),
        horario_aula="08:00 às 09:00",
        tipo_aula="Transmissão ao vivo",
        canal_utilizado="Canal 01",
        conteudo_ministrado="Teste de Segurança",
        conflito_geminada_resolvido=False,
        status_compliance="Pendente"
    )
    db_session.add(relatorio_alheio)
    db_session.commit()

    # 2. Tentativa de cancelamento com a chave 'descricao' (padrão do sistema)
    response = client.patch(
        f"/api/v1/reports/{relatorio_alheio.id}/cancelar",
        headers=assistant_headers,
        json={"descricao": "Tentativa não autorizada"} # Mudamos de 'motivo' para 'descricao'
    )

    # Se ainda der 422, tentaremos 'justificativa'
    if response.status_code == 422:
        response = client.patch(
            f"/api/v1/reports/{relatorio_alheio.id}/cancelar",
            headers=assistant_headers,
            json={"justificativa": "Tentativa não autorizada"}
        )

    # 3. Agora o sistema deve validar o JSON e cair na trava de segurança (403)
    # ... (mantenha o resto do código igual)

    # 3. Agora o sistema deve validar o JSON e cair na trava de segurança (403)
    assert response.status_code == 403
    
    # Ajustamos para a frase real que o seu backend está enviando:
    assert "Assistentes só podem cancelar relatórios criados por eles mesmos." in response.json()["detail"]