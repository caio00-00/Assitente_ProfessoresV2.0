from app.tasks.worker import verificar_compliance_drive

def test_trava_100mb_deve_marcar_como_pendente(db_session, sample_turma, assistant_user):
    # 1. Criar um relatório no banco
    # 2. Mockar a resposta do Google Drive para retornar 50MB
    # 3. Chamar a função de compliance
    # 4. Verificar se o status_compliance no banco virou "Pendente"
    pass # Eu posso te ajudar a escrever o Mock completo se você quiser!