"""Filtros da Auditoria, do Histórico do Diretor de Imagem e da exportação."""

import uuid
from datetime import date, datetime, timedelta, timezone

from app.core.security import create_access_token, get_password_hash
from app.models.auxiliares import Professor, ProfessorDisciplina
from app.models.class_report import ClassReport
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import ImageDirectorLesson, ImageDirectorReport
from app.models.user import User


def _cr(db, turma, disc, **kw):
    base = dict(
        created_by=uuid.uuid4(), status="AGUARDANDO_VALIDACAO", data_aula=date(2026, 9, 7), turno="Manhã",
        estudio="ESTÚDIO 3", turma_id=turma.id, disciplina_id=disc.id, horario_aula="1º Horário",
        tipo_aula="Transmissão ao vivo", canal_utilizado="1", conteudo_ministrado="X", status_compliance="Pendente",
    )
    base.update(kw)
    r = ClassReport(**base)
    db.add(r)
    db.commit()
    return r


def _chefe(db):
    u = User(email="chefe_f@test.com", full_name="Chefe", role="diretor_chefe",
             hashed_password=get_password_hash("x"), email_confirmed=True)
    db.add(u)
    db.flush()
    d = DiretorImagem(nome="Dir F", user_id=u.id, is_active=True)
    db.add(d)
    db.commit()
    token = create_access_token(data={"sub": u.email, "role": u.role, "user_id": str(u.id)})
    return u, d, {"Authorization": f"Bearer {token}"}


def test_filtro_estudio_aceita_grafias_diferentes(client, admin_headers, db_session, sample_turma,
                                                  sample_professor_disciplina):
    disc = sample_professor_disciplina["disciplina"]
    _cr(db_session, sample_turma, disc, estudio="ESTÚDIO 3", horario_aula="1º Horário")
    _cr(db_session, sample_turma, disc, estudio="Estúdio 03", horario_aula="2º Horário")
    _cr(db_session, sample_turma, disc, estudio="ESTÚDIO 1", horario_aula="3º Horário")
    res = client.get("/api/v1/reports/", params={"estudio": "Estúdio 03"}, headers=admin_headers)
    assert res.json()["total"] == 2


def test_filtro_professor_pega_cadastro_duplicado_e_nome_externo(client, admin_headers, db_session, sample_turma,
                                                               sample_professor_disciplina):
    prof, disc = sample_professor_disciplina["professor"], sample_professor_disciplina["disciplina"]
    dup = Professor(nome="JOAO SILVA")  # mesmo professor cadastrado 2x (grafia diferente)
    db_session.add(dup)
    db_session.flush()
    db_session.add(ProfessorDisciplina(professor_id=dup.id, disciplina_id=disc.id))
    db_session.commit()
    _cr(db_session, sample_turma, disc, professor_id=prof.id, horario_aula="1º Horário")
    _cr(db_session, sample_turma, disc, professor_id=dup.id, horario_aula="2º Horário")
    _cr(db_session, sample_turma, disc, professor_nome_externo=prof.nome.upper(), horario_aula="3º Horário")
    _cr(db_session, sample_turma, disc, professor_id=None, horario_aula="4º Horário")
    res = client.get("/api/v1/reports/", params={"professor_id": str(prof.id)}, headers=admin_headers)
    assert res.json()["total"] == 3


def test_periodo_invertido_retorna_422(client, admin_headers):
    res = client.get("/api/v1/reports/", params={"data_inicio": "2026-09-10", "data_fim": "2026-09-01"},
                     headers=admin_headers)
    assert res.status_code == 422
    assert "data de início" in res.json()["detail"]


def test_auditoria_unificada_total_e_paginacao(client, db_session, sample_turma, sample_professor_disciplina):
    user, diretor, headers = _chefe(db_session)
    disc = sample_professor_disciplina["disciplina"]
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)
    for i in range(3):
        _cr(db_session, sample_turma, disc, data_aula=date(2026, 9, 1 + i * 2), horario_aula=f"{i + 1}º Horário",
            created_at=base + timedelta(hours=i))
    # 2 relatórios só do diretor (sem relatório de aula) em datas intercaladas
    for dia in (2, 4):
        db_session.add(ImageDirectorReport(created_by=user.id, diretor_imagem_id=diretor.id,
                                           data_relatorio=date(2026, 9, dia), turno="Manhã", estudio="ESTÚDIO 3",
                                           turma_id=sample_turma.id, horario_aula="1º Horário", origem="nova_aula"))
    db_session.commit()

    res = client.get("/api/v1/reports/auditoria", params={"limit": 2, "offset": 0}, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 5
    datas = []
    for off in (0, 2, 4):
        page = client.get("/api/v1/reports/auditoria", params={"limit": 2, "offset": off}, headers=headers).json()
        for it in page["items"]:
            datas.append(it["data"].get("data_aula") or it["data"].get("data_relatorio"))
    assert datas == ["2026-09-05", "2026-09-04", "2026-09-03", "2026-09-02", "2026-09-01"]

    # Filtro que só existe no relatório do assistente remove as linhas "só diretor"
    so_assist = client.get("/api/v1/reports/auditoria", params={"status": "AGUARDANDO_VALIDACAO"},
                           headers=headers).json()
    assert so_assist["total"] == 3
    assert all(it["tipo"] == "class" for it in so_assist["items"])


def test_historico_idr_filtra_professor_e_disciplina_das_aulas(client, db_session, sample_turma,
                                                              sample_professor_disciplina):
    user, diretor, headers = _chefe(db_session)
    prof, disc = sample_professor_disciplina["professor"], sample_professor_disciplina["disciplina"]
    r1 = ImageDirectorReport(created_by=user.id, diretor_imagem_id=diretor.id, data_relatorio=date(2026, 9, 7),
                             turno="Manhã", estudio="ESTÚDIO 3", turma_id=sample_turma.id, horario_aula="1º Horário")
    r2 = ImageDirectorReport(created_by=user.id, diretor_imagem_id=diretor.id, data_relatorio=date(2026, 9, 7),
                             turno="Manhã", estudio="ESTÚDIO 3", turma_id=sample_turma.id, horario_aula="2º Horário")
    db_session.add_all([r1, r2])
    db_session.flush()
    db_session.add(ImageDirectorLesson(report_id=r1.id, numero_aula=1, disciplina_nome=disc.nome,
                                       professor_nome=prof.nome, transmissao_ou_gravada="Aula gravada"))
    db_session.add(ImageDirectorLesson(report_id=r2.id, numero_aula=1, disciplina_nome="OUTRA",
                                       professor_nome="Outro Prof", transmissao_ou_gravada="Aula gravada"))
    db_session.commit()
    por_prof = client.get("/api/v1/image-director/", params={"professor_id": str(prof.id)}, headers=headers).json()
    assert [i["id"] for i in por_prof["items"]] == [str(r1.id)]
    por_disc = client.get("/api/v1/image-director/", params={"disciplina_id": str(disc.id)}, headers=headers).json()
    assert [i["id"] for i in por_disc["items"]] == [str(r1.id)]
    por_estudio = client.get("/api/v1/image-director/", params={"estudio": "Estúdio 03"}, headers=headers).json()
    assert por_estudio["total"] == 2


def test_exportacao_respeita_filtro_de_estudio(client, admin_headers, db_session, sample_turma,
                                               sample_professor_disciplina):
    disc = sample_professor_disciplina["disciplina"]
    _cr(db_session, sample_turma, disc, estudio="ESTÚDIO 3")
    res = client.get("/api/v1/reports/export", params={"estudio": "Estúdio 03"}, headers=admin_headers)
    assert res.status_code == 200


def test_lookup_usuarios_so_quem_tem_relatorio_e_desambigua(client, admin_headers, db_session, sample_turma,
                                                          sample_professor_disciplina):
    disc = sample_professor_disciplina["disciplina"]
    com = User(email="iracema1@test.com", full_name="Iracema Pinheiro", role="assistente",
               hashed_password=get_password_hash("x"), email_confirmed=True)
    sem = User(email="iracema2@test.com", full_name="Iracema Pinheiro", role="assistente",
               hashed_password=get_password_hash("x"), email_confirmed=True)
    db_session.add_all([com, sem])
    db_session.commit()
    _cr(db_session, sample_turma, disc, created_by=com.id)
    nomes = client.get("/api/v1/reports/lookup/users", headers=admin_headers).json()
    assert [n["id"] for n in nomes] == [str(com.id)]
    assert nomes[0]["nome"] == "Iracema Pinheiro"

    # Duas contas com o mesmo nome e ambas com relatórios → e-mail para diferenciar
    _cr(db_session, sample_turma, disc, created_by=sem.id, horario_aula="2º Horário")
    nomes = client.get("/api/v1/reports/lookup/users", headers=admin_headers).json()
    assert sorted(n["nome"] for n in nomes) == [
        "Iracema Pinheiro (iracema1@test.com)", "Iracema Pinheiro (iracema2@test.com)",
    ]


def test_tooltip_grade_campos_de_diretor_e_professor(client, db_session, sample_turma, sample_professor_disciplina,
                                                     admin_headers):
    """Dados usados no tooltip da Grade: nome do diretor no relatório de aula e professor no do diretor."""
    user, diretor, headers = _chefe(db_session)
    prof, disc = sample_professor_disciplina["professor"], sample_professor_disciplina["disciplina"]
    cr = _cr(db_session, sample_turma, disc, professor_id=prof.id, status="VALIDADO")
    db_session.add(ImageDirectorReport(created_by=user.id, diretor_imagem_id=diretor.id, data_relatorio=cr.data_aula,
                                       turno="Manhã", estudio="ESTÚDIO 3", turma_id=sample_turma.id,
                                       horario_aula="1º Horário", class_report_id=cr.id, status="VALIDADO",
                                       professor_id=prof.id))
    db_session.commit()
    item = client.get("/api/v1/reports/", headers=admin_headers).json()["items"][0]
    assert item["image_director_diretor_nome"] == "Dir F"
    idr = client.get("/api/v1/image-director/", headers=headers).json()["items"][0]
    assert idr["professor_nome"] == prof.nome


def test_filtros_modalidade_e_status_idr(client, admin_headers, db_session, sample_turma, sample_professor_disciplina):
    user, diretor, headers = _chefe(db_session)
    disc = sample_professor_disciplina["disciplina"]
    grav = _cr(db_session, sample_turma, disc, tipo_aula="Gravação estúdio", horario_aula="1º Horário")
    trans = _cr(db_session, sample_turma, disc, tipo_aula="Transmissão ao vivo", horario_aula="2º Horário")
    db_session.add(ImageDirectorReport(created_by=user.id, diretor_imagem_id=diretor.id, data_relatorio=grav.data_aula,
                                       turno="Manhã", estudio="ESTÚDIO 3", turma_id=sample_turma.id,
                                       horario_aula="1º Horário", class_report_id=grav.id, status="VALIDADO"))
    db_session.commit()

    def ids(params, h=admin_headers, url="/api/v1/reports/"):
        return {i["id"] for i in client.get(url, params=params, headers=h).json()["items"]}

    assert ids({"modalidade_aula": "gravacao"}) == {str(grav.id)}
    assert ids({"modalidade_aula": "transmissao"}) == {str(trans.id)}
    assert ids({"status_idr": "VALIDADO"}) == {str(grav.id)}
    assert ids({"status_idr": "SEM_RELATORIO"}) == {str(trans.id)}
    assert client.get("/api/v1/reports/", params={"modalidade_aula": "x"}, headers=admin_headers).status_code == 422
    aud = client.get("/api/v1/reports/auditoria", params={"status_idr": "VALIDADO"}, headers=headers).json()
    assert [i["data"]["id"] for i in aud["items"]] == [str(grav.id)]
    assert client.get("/api/v1/reports/export", params={"status_idr": "VALIDADO", "modalidade_aula": "gravacao"},
                      headers=admin_headers).status_code == 200


def test_migrar_finalizados_so_aulas_a_partir_de_01_09(client, admin_headers, db_session, sample_turma,
                                                      sample_professor_disciplina):
    disc = sample_professor_disciplina["disciplina"]
    antigo = _cr(db_session, sample_turma, disc, status="FINALIZADO", data_aula=date(2026, 8, 31))
    antecipado = _cr(db_session, sample_turma, disc, status="FINALIZADO", data_aula=date(2026, 9, 9))
    url = "/api/v1/reports/admin/finalizados-para-validacao"
    sim = client.post(url, headers=admin_headers).json()
    assert sim["aplicado"] is False and [r["id"] for r in sim["relatorios"]] == [str(antecipado.id)]
    db_session.expire_all()
    assert db_session.get(ClassReport, antecipado.id).status == "FINALIZADO"
    feito = client.post(url, params={"aplicar": "true"}, headers=admin_headers).json()
    assert feito["aplicado"] is True and feito["total"] == 1
    db_session.expire_all()
    assert db_session.get(ClassReport, antecipado.id).status == "AGUARDANDO_VALIDACAO"
    assert db_session.get(ClassReport, antigo.id).status == "FINALIZADO"
    assert client.post(url, params={"aplicar": "true"}, headers=admin_headers).json()["total"] == 0


def test_compliance_verde_quando_tem_video_e_pdf(client, admin_headers, db_session, sample_turma,
                                                sample_professor_disciplina):
    from unittest.mock import patch

    from app.services.compliance import corrigir_verdes_pendentes

    disc = sample_professor_disciplina["disciplina"]
    drive = _cr(db_session, sample_turma, disc, status_compliance="Vermelho", horario_aula="1º Horário",
                video_link="https://drive/v", slide_link="https://drive/s")
    so_vimeo = _cr(db_session, sample_turma, disc, status_compliance="Pendente", horario_aula="2º Horário",
                   vimeo_link="https://vimeo/1", slide_link="https://drive/s2")
    sem_pdf = _cr(db_session, sample_turma, disc, status_compliance="Vermelho", horario_aula="3º Horário",
                  video_link="https://drive/v3")
    assert corrigir_verdes_pendentes(db_session) == 1
    db_session.expire_all()
    assert db_session.get(ClassReport, drive.id).status_compliance == "Verde"
    # Vimeo não conta: vídeo e PDF precisam estar no Drive
    assert db_session.get(ClassReport, so_vimeo.id).status_compliance == "Pendente"
    assert db_session.get(ClassReport, sem_pdf.id).status_compliance == "Vermelho"

    # Botão "Sincronizar Tudo" corrige na hora
    sem_pdf.slide_link = "https://drive/s3"
    db_session.commit()
    from app.tasks import worker
    with patch.object(worker.sincronizacao_noturna_drive, "delay"):
        res = client.post("/api/v1/reports/force-sync-drive", headers=admin_headers)
    assert res.status_code == 202 and res.json()["corrigidos_verde"] == 1


def test_worker_fica_verde_quando_video_do_drive_ja_existe_e_acha_o_pdf(db_session, sample_turma,
                                                                        sample_professor_disciplina):
    """Relatório Vermelho com vídeo no Drive: ao achar o PDF, vira Verde (não fica Vermelho)."""
    from unittest.mock import patch

    from app.tasks import worker

    disc = sample_professor_disciplina["disciplina"]
    r = _cr(db_session, sample_turma, disc, status_compliance="Vermelho", nome_ficheiro_gerado="X.mp4",
            video_link="https://drive/v")
    rid = r.id
    with patch.object(worker, "SessionLocal", return_value=db_session), \
            patch.object(worker, "buscar_slide_no_drive", return_value={"webViewLink": "https://drive/pdf", "name": "X.pdf"}):
        ok = worker.verificar_compliance_drive.run(rid, "X.mp4")
    assert ok is True
    assert db_session.get(ClassReport, rid).status_compliance == "Verde"


def test_status_resumo_conta_cada_status_com_os_filtros_da_lista(client, admin_headers, db_session, sample_turma,
                                                                sample_professor_disciplina):
    disc = sample_professor_disciplina["disciplina"]
    _cr(db_session, sample_turma, disc, status="RASCUNHO", horario_aula="1º Horário")
    _cr(db_session, sample_turma, disc, status="RASCUNHO", horario_aula="2º Horário", precisa_correcao=True)
    _cr(db_session, sample_turma, disc, status="AGUARDANDO_VALIDACAO", horario_aula="3º Horário")
    _cr(db_session, sample_turma, disc, status="VALIDADO", horario_aula="4º Horário")
    _cr(db_session, sample_turma, disc, status="VALIDADO", horario_aula="5º Horário", estudio="ESTÚDIO 1")
    _cr(db_session, sample_turma, disc, status="CANCELADO", horario_aula="6º Horário")
    _cr(db_session, sample_turma, disc, status="VALIDADO", horario_aula="1º Horário", data_aula=date(2026, 9, 8))

    url = "/api/v1/reports/status-resumo"
    dia = {"data_inicio": "2026-09-07", "data_fim": "2026-09-07"}
    r = client.get(url, params=dia, headers=admin_headers).json()
    assert r["rascunho"] == 2 and r["aguardando_validacao"] == 1 and r["validado"] == 2
    assert r["cancelado"] == 1 and r["precisa_correcao"] == 1
    assert r["faltam_validar"] == 3 and r["total"] == 6

    # O filtro de status da lista não muda os cards; os outros filtros sim.
    r = client.get(url, params={**dia, "status": "VALIDADO", "estudio": "Estúdio 03"}, headers=admin_headers).json()
    assert r["validado"] == 1 and r["rascunho"] == 2 and r["total"] == 5

    # Mesma contagem que a lista mostra ao escolher o status.
    lista = client.get("/api/v1/reports/", params={**dia, "status": "RASCUNHO"}, headers=admin_headers).json()
    assert lista["total"] == 2
