"""
Reunião de out/2026 (antecipada × reposição, cobrança SEDUC, vídeo corrompido, links):
- Agenda: o diretor-chefe informa se é pedido da SEDUC (chamado obrigatório) e liga a
  gravação antecipada à aula da grade que vai ao ar;
- a exibição dessa aula aponta para a gravação (não vira outra gravação);
- data da gravação define o mês (reposição gravada depois entra no mês da gravação);
- faturamento: SEDUC cobra gravação + exibição, Canal/professor só a exibição;
- busca dos links só depois do diretor finalizar e sem vídeo corrompido;
- coordenação só valida com os dois links; chefe não valida vídeo corrompido;
- coleta aceita outros formatos de vídeo/slide.
"""
import uuid
from datetime import date, time
from types import SimpleNamespace

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.auxiliares import Disciplina, Grade
from app.models.class_report import ClassReport
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import ImageDirectorLesson, ImageDirectorReport
from app.models.infraestrutura import Estudio
from app.models.turma import Turma
from app.models.user import User

AG = "/api/v1/agenda-estudios"
SEG = date(2026, 10, 26)     # segunda — dia da gravação antecipada
QUA = date(2026, 10, 28)     # quarta — a aula da grade vai ao ar com a gravação


def _user(db, role, email, diretor=False):
    u = User(email=email, full_name=email, role=role, hashed_password=get_password_hash("x"), email_confirmed=True)
    db.add(u)
    db.flush()
    d = None
    if diretor:
        d = DiretorImagem(nome=email.split("@")[0].upper(), user_id=u.id, is_active=True)
        db.add(d)
    db.commit()
    h = {"Authorization": f"Bearer {create_access_token(data={'sub': u.email, 'role': u.role, 'user_id': str(u.id)})}"}
    return h, d


def _cenario(db):
    e1 = Estudio(nome="ESTÚDIO 1", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    e2 = Estudio(nome="ESTÚDIO 2", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    t = Turma(nome="EM 2 MANHÃ", modalidade="REGULAR", serie_modulo="2", turno="MANHÃ", nomenclatura_padrao="EM 2 MANHÃ")
    d = Disciplina(nome="QUÍMICA")
    db.add_all([e1, e2, t, d])
    db.flush()
    g = Grade(turma_id=t.id, disciplina_id=d.id, estudio_id=e1.id, dia_semana=2,   # quarta
              horario_inicio=time(8, 30), horario_fim=time(9, 30))
    db.add(g)
    db.commit()
    return dict(e1=e1, e2=e2, t=t, d=d, g=g)


def _antecipada(s, **extra):
    corpo = {"data": SEG.isoformat(), "estudio_id": s["e2"].id, "horario_inicio": "14:00", "horario_fim": "15:00",
             "tipo": "GRAVACAO_ANTECIPADA", "titulo": "Química (vai ao ar quarta)", "turma_id": str(s["t"].id),
             "confirmar_avisos": True}
    corpo.update(extra)
    return corpo


# ─── Agenda: pedido da SEDUC e ligação com a aula da grade ─────────────

def test_agenda_seduc_obriga_chamado_e_canal_nao(client, db_session, admin_headers):
    s = _cenario(db_session)
    r = client.post(f"{AG}/agendamentos", json=_antecipada(s, solicitante_antecipacao="SEDUC"), headers=admin_headers)
    assert r.status_code == 422 and "chamado" in r.json()["detail"].lower()
    r = client.post(f"{AG}/agendamentos", json=_antecipada(s, solicitante_antecipacao="PROFESSOR"), headers=admin_headers)
    assert r.status_code == 201, r.text
    assert r.json()["solicitante_antecipacao"] == "PROFESSOR"
    r = client.post(f"{AG}/agendamentos", json=_antecipada(s, solicitante_antecipacao="QUALQUER",
                                                           horario_inicio="16:00", horario_fim="17:00"),
                    headers=admin_headers)
    assert r.status_code == 422


def test_agenda_caixa_seduc_vale_para_todo_agendamento(client, db_session, admin_headers):
    """Reunião 26/10: a caixa SEDUC aparece em todo agendamento (marcada = chamado obrigatório)."""
    s = _cenario(db_session)
    corpo = _antecipada(s, tipo="AULA_EXTRA", solicitante_antecipacao="SEDUC", chamado="123",
                        data_referencia=QUA.isoformat())
    r = client.post(f"{AG}/agendamentos", json=corpo, headers=admin_headers)
    assert r.status_code == 201, r.text
    # SEDUC vale; data de referência só existe em gravação
    assert r.json()["solicitante_antecipacao"] == "SEDUC" and r.json()["data_referencia"] is None
    ev = {"data": SEG.isoformat(), "estudio_id": s["e1"].id, "horario_inicio": "10:00", "horario_fim": "11:00",
          "tipo": "EVENTO", "titulo": "Live", "nome_evento": "Live SEDUC", "solicitante_antecipacao": "SEDUC",
          "chamado": "777", "confirmar_avisos": True}
    r = client.post(f"{AG}/agendamentos", json=ev, headers=admin_headers)
    assert r.status_code == 201, r.text
    assert r.json()["solicitante_antecipacao"] == "SEDUC"


def test_antecipada_exibicao_depois_da_gravacao_e_aula_da_grade(client, db_session, admin_headers):
    s = _cenario(db_session)
    # exibição antes da gravação não é antecipada
    r = client.post(f"{AG}/agendamentos", json=_antecipada(s, data_referencia="2026-10-20"), headers=admin_headers)
    assert r.status_code == 422
    # aula que não é da turma naquela data
    r = client.post(f"{AG}/agendamentos", json=_antecipada(s, data_referencia="2026-10-29",
                                                           grade_exibicao_id=str(s["g"].id)), headers=admin_headers)
    assert r.status_code == 422
    # o chefe escolhe a aula pela lista
    aulas = client.get(f"{AG}/aulas-da-turma", params={"turma_id": str(s["t"].id), "data": QUA.isoformat()},
                       headers=admin_headers).json()
    assert [a["grade_id"] for a in aulas] == [str(s["g"].id)] and "QUÍMICA" in aulas[0]["descricao"]
    r = client.post(f"{AG}/agendamentos", json=_antecipada(s, data_referencia=QUA.isoformat(),
                                                           grade_exibicao_id=str(s["g"].id),
                                                           solicitante_antecipacao="SEDUC", chamado="18097"),
                    headers=admin_headers)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["grade_exibicao_id"] == str(s["g"].id) and j["data_referencia"] == QUA.isoformat()
    # editar mantém tudo
    j2 = client.put(f"{AG}/agendamentos/{j['id']}", json=_antecipada(s, data_referencia=QUA.isoformat(),
                                                                       grade_exibicao_id=str(s["g"].id),
                                                                       solicitante_antecipacao="SEDUC", chamado="18097"),
                    headers=admin_headers)
    assert j2.status_code == 200, j2.text
    assert j2.json()["grade_exibicao_id"] == str(s["g"].id) and j2.json()["solicitante_antecipacao"] == "SEDUC"


def test_exibicao_aponta_para_gravacao_no_relatorio_do_diretor(client, db_session, admin_headers):
    s = _cenario(db_session)
    a = client.post(f"{AG}/agendamentos", json=_antecipada(s, data_referencia=QUA.isoformat(),
                                                           grade_exibicao_id=str(s["g"].id),
                                                           solicitante_antecipacao="SEDUC", chamado="18097"),
                    headers=admin_headers)
    assert a.status_code == 201, a.text
    r = client.get(f"{AG}/estudio-da-aula", params={"turma_id": str(s["t"].id), "data": QUA.isoformat(),
                                                    "inicio": "08:30"}, headers=admin_headers).json()
    ex = r["exibicao_antecipada"]
    assert ex and ex["data_gravacao"] == SEG.isoformat() and ex["solicitante"] == "SEDUC" and ex["chamado"] == "18097"
    # na quarta seguinte a aula é normal
    r2 = client.get(f"{AG}/estudio-da-aula", params={"turma_id": str(s["t"].id), "data": "2026-11-04",
                                                     "inicio": "08:30"}, headers=admin_headers).json()
    assert r2["exibicao_antecipada"] is None
    # o relatório do diretor da exibição herda da Agenda
    hd, d = _user(db_session, "diretor_imagem", "ana@t.com", diretor=True)
    p = {"diretor_imagem_id": str(d.id), "data_relatorio": QUA.isoformat(), "turno": "Manhã", "estudio": "ESTÚDIO 1",
         "turma_id": str(s["t"].id), "disciplina_id": str(s["d"].id), "disciplina_nome": "QUÍMICA",
         "professor_nome_externo": "Prof. Bia", "horario_aula": "08:30 às 09:30", "origem": "grade"}
    idr = client.post("/api/v1/image-director/", json=p, headers=hd)
    assert idr.status_code == 201, idr.text
    j = idr.json()
    assert j["solicitante_antecipacao"] == "SEDUC" and j["ticket_number"] == "18097"
    assert j["motivo_referencia"] == "Exibição da aula gravada antecipadamente em 26/10/2026"


def test_relatorio_do_diretor_usa_solicitacao_da_agenda(client, db_session, admin_headers):
    """O que o chefe marcou na Agenda vale mais que o que vier no formulário."""
    s = _cenario(db_session)
    client.post(f"{AG}/agendamentos", json=_antecipada(s, solicitante_antecipacao="PROFESSOR"), headers=admin_headers)
    hd, d = _user(db_session, "diretor_imagem", "rui@t.com", diretor=True)
    p = {"diretor_imagem_id": str(d.id), "data_relatorio": SEG.isoformat(), "turno": "Tarde", "estudio": "ESTÚDIO 2",
         "turma_id": str(s["t"].id), "disciplina_nome": "QUÍMICA", "professor_nome_externo": "Prof. Bia",
         "horario_aula": "14:00 às 15:00", "origem": "grade", "solicitante_antecipacao": "SEDUC"}
    j = client.post("/api/v1/image-director/", json=p, headers=hd)
    assert j.status_code == 201, j.text  # SEDUC sem chamado não trava mais o diretor
    assert j.json()["solicitante_antecipacao"] == "PROFESSOR"


# ─── Datas: gravação × aula na grade ───────────────────────────────────

def _cr_obj(**kw):
    base = dict(data_aula=date(2026, 10, 30), data_execucao_real=None, data_referencia_aula=None, motivo_referencia=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_ajustar_datas_reposicao_antecipada_e_igual():
    from app.services.image_director_associacao import ajustar_datas_gravacao

    r = _cr_obj(data_execucao_real=date(2026, 11, 3))       # aula de 30/10 gravada em 03/11
    ajustar_datas_gravacao(r)
    assert r.data_referencia_aula == date(2026, 10, 30)
    assert r.motivo_referencia == "Gravação por reposição/falta, referente à aula do dia 30/10/2026"

    r = _cr_obj(data_execucao_real=date(2026, 10, 27))      # gravada antes
    ajustar_datas_gravacao(r)
    assert r.motivo_referencia == "Gravação antecipada da aula do dia 30/10/2026"

    r.data_execucao_real = date(2026, 10, 30)                # voltou a ser no próprio dia
    ajustar_datas_gravacao(r)
    assert r.data_referencia_aula is None and r.motivo_referencia is None

    # registro antigo: só a referência (antecipada marcada na Agenda)
    r = _cr_obj(data_aula=date(2026, 10, 26), data_referencia_aula=date(2026, 10, 28))
    ajustar_datas_gravacao(r)
    assert r.data_execucao_real == date(2026, 10, 26)
    assert r.motivo_referencia == "Gravação antecipada da aula do dia 28/10/2026"


def _cr(db, s, user_id, **kw):
    base = dict(created_by=user_id, status="AGUARDANDO_VALIDACAO", data_aula=date(2026, 10, 30), turno="Manhã",
                estudio="ESTÚDIO 1", turma_id=s["t"].id, disciplina_id=s["d"].id, horario_aula="08:30 às 09:30",
                start_time=time(8, 30), end_time=time(9, 30), tipo_aula="Gravação estúdio", canal_utilizado="N/A",
                conteudo_ministrado="Reações", status_compliance="Pendente", nome_ficheiro_gerado="EM 2 QUIMICA X.mp4")
    base.update(kw)
    r = ClassReport(**base)
    db.add(r)
    db.commit()
    return r


def test_export_usa_mes_da_gravacao_e_pareia_com_o_diretor(db_session, admin_user):
    from app.services.audit_export import _build_pairings, _load_class_reports
    from app.services.audit_export import AuditExportFilters

    s = _cenario(db_session)
    cr = _cr(db_session, s, admin_user.id, data_execucao_real=date(2026, 11, 3),
             data_referencia_aula=date(2026, 10, 30))
    outubro = AuditExportFilters(data_inicio=date(2026, 10, 1), data_fim=date(2026, 10, 31))
    novembro = AuditExportFilters(data_inicio=date(2026, 11, 1), data_fim=date(2026, 11, 30))
    assert cr.id not in {r.id for r in _load_class_reports(db_session, outubro)}
    assert cr.id in {r.id for r in _load_class_reports(db_session, novembro)}
    # o diretor registrou no dia da gravação
    d = DiretorImagem(nome="ANA", is_active=True)
    db_session.add(d)
    db_session.flush()
    idr = ImageDirectorReport(created_by=admin_user.id, diretor_imagem_id=d.id, data_relatorio=date(2026, 11, 3),
                              turno="Manhã", estudio="Estúdio 01", turma_id=s["t"].id, disciplina_id=s["d"].id,
                              horario_aula="Gravação", origem="grade", status="AGUARDANDO_VALIDACAO")
    db_session.add(idr)
    db_session.commit()
    rows, _ = _build_pairings([cr], [idr])
    assert rows == [(cr, idr)]


# ─── Cobrança ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("cr_kw,esperado", [
    (dict(data_aula=date(2026, 10, 26), data_execucao_real=date(2026, 10, 26),
          data_referencia_aula=date(2026, 10, 28), solicitante_antecipacao="SEDUC"),
     ("GRAVAÇÃO ANTECIPADA", "Sim")),
    (dict(data_aula=date(2026, 10, 26), data_execucao_real=date(2026, 10, 26),
          data_referencia_aula=date(2026, 10, 28), solicitante_antecipacao="PROFESSOR"),
     ("GRAVAÇÃO ANTECIPADA", "Não (cobra só a exibição)")),
    (dict(data_aula=date(2026, 10, 28), solicitante_antecipacao="PROFESSOR",
          motivo_referencia="Exibição da aula gravada antecipadamente em 26/10/2026"),
     ("EXIBIÇÃO DE AULA ANTECIPADA", "Sim")),
    (dict(data_aula=date(2026, 10, 30), data_execucao_real=date(2026, 11, 3),
          data_referencia_aula=date(2026, 10, 30)),
     ("REPOSIÇÃO", "Sim")),
    (dict(data_aula=date(2026, 10, 30)), ("AULA", "Sim")),
])
def test_classificar_lancamento(cr_kw, esperado):
    from app.services.audit_export import classificar_lancamento

    base = dict(data_execucao_real=None, data_referencia_aula=None, solicitante_antecipacao=None, motivo_referencia=None)
    base.update(cr_kw)
    assert classificar_lancamento(SimpleNamespace(**base), None) == esperado


def test_classificar_lancamento_so_com_relatorio_do_diretor():
    from app.services.audit_export import classificar_lancamento

    idr = SimpleNamespace(data_relatorio=date(2026, 10, 26), data_referencia=date(2026, 10, 28),
                          solicitante_antecipacao="SEDUC", motivo_referencia=None)
    assert classificar_lancamento(None, idr) == ("GRAVAÇÃO ANTECIPADA", "Sim")


def test_planilha_de_faturamento_tem_lancamento_e_cobrar(db_session, admin_user):
    import io

    from openpyxl import load_workbook

    from app.services.audit_export import AuditExportFilters
    from app.services.audit_export import build_audit_workbook

    s = _cenario(db_session)
    cr = _cr(db_session, s, admin_user.id, data_aula=date(2026, 10, 26), data_execucao_real=date(2026, 10, 26),
             data_referencia_aula=date(2026, 10, 28), solicitante_antecipacao="PROFESSOR")

    def _planilha():
        out = build_audit_workbook(db_session, AuditExportFilters(), include_faturamento=True)
        data = out if isinstance(out, (bytes, bytearray)) else out[0]
        ws = load_workbook(io.BytesIO(data))["Faturamento SEDUC"]
        cab = [c.value for c in ws[1]]
        return cab, [c.value for c in ws[2]]

    # v4: enquanto não está validado, a cobrança fica pendente
    cab, linha = _planilha()
    assert linha[cab.index("LANÇAMENTO")] == "GRAVAÇÃO ANTECIPADA"
    assert linha[cab.index("COBRAR")].startswith("Pendente")

    # validado: vale a regra de cobrança
    cr.status = "VALIDADO"
    db_session.commit()
    cab, linha = _planilha()
    assert linha[cab.index("COBRAR")] == "Não (cobra só a exibição)"

    # cancelado: não cobra
    cr.status = "CANCELADO"
    db_session.commit()
    cab, linha = _planilha()
    assert linha[cab.index("COBRAR")] == "Não (cancelado)"


# ─── Busca dos links × diretor de imagem ───────────────────────────────

def _idr_com_aula(db, s, user_id, cr, status="RASCUNHO", corrompido="Não"):
    d = DiretorImagem(nome=f"D{uuid.uuid4().hex[:4]}", is_active=True)
    db.add(d)
    db.flush()
    idr = ImageDirectorReport(created_by=user_id, diretor_imagem_id=d.id, data_relatorio=cr.data_aula,
                              turno="Manhã", estudio="ESTÚDIO 1", turma_id=s["t"].id, disciplina_id=s["d"].id,
                              horario_aula="08:30 às 09:30", origem="grade", status=status, class_report_id=cr.id,
                              youtube_link="https://youtu.be/x")
    db.add(idr)
    db.flush()
    db.add(ImageDirectorLesson(report_id=idr.id, numero_aula=1, class_report_id=cr.id, disciplina_nome="QUÍMICA",
                               professor_nome="Prof. Bia", transmissao_ou_gravada="Aula gravada",
                               video_corrompido=corrompido,
                               video_corrompido_obs="travou" if corrompido == "Sim" else None))
    db.commit()
    db.refresh(idr)
    return idr


def test_bloqueio_da_busca_de_links(db_session, admin_user):
    from app.services.busca_links import AGUARDANDO_FINALIZAR, VIDEO_CORROMPIDO, bloqueio_busca_link

    s = _cenario(db_session)
    cr = _cr(db_session, s, admin_user.id)
    assert bloqueio_busca_link(db_session, cr) is None      # sem relatório do diretor: regra de antes
    idr = _idr_com_aula(db_session, s, admin_user.id, cr)
    assert bloqueio_busca_link(db_session, cr) == AGUARDANDO_FINALIZAR
    assert bloqueio_busca_link(db_session, cr, exigir_diretor=False) is None   # "Reverificar" da coordenação
    idr.status = "AGUARDANDO_VALIDACAO"
    idr.lessons[0].video_corrompido = "Sim"
    db_session.commit()
    assert bloqueio_busca_link(db_session, cr) == VIDEO_CORROMPIDO
    assert bloqueio_busca_link(db_session, cr, exigir_diretor=False) == VIDEO_CORROMPIDO
    idr.lessons[0].video_corrompido = "Não"
    db_session.commit()
    assert bloqueio_busca_link(db_session, cr) is None


def test_worker_nao_busca_com_video_corrompido(db_session, admin_user, monkeypatch):
    import app.tasks.worker as worker
    from tests.conftest import TestingSessionLocal

    s = _cenario(db_session)
    cr = _cr(db_session, s, admin_user.id)
    _idr_com_aula(db_session, s, admin_user.id, cr, status="AGUARDANDO_VALIDACAO", corrompido="Sim")

    def nao_pode(*a, **k):
        raise AssertionError("não devia buscar no Drive com vídeo corrompido")

    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "buscar_video_no_drive", nao_pode)
    monkeypatch.setattr(worker, "buscar_slide_no_drive", nao_pode)
    assert worker.verificar_compliance_drive.run(cr.id, cr.nome_ficheiro_gerado) is False


def test_worker_busca_quando_diretor_liberou(db_session, admin_user, monkeypatch):
    import app.tasks.worker as worker
    from tests.conftest import TestingSessionLocal

    s = _cenario(db_session)
    cr = _cr(db_session, s, admin_user.id)
    _idr_com_aula(db_session, s, admin_user.id, cr, status="AGUARDANDO_VALIDACAO")
    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "buscar_slide_no_drive", lambda n: {"webViewLink": "https://drive/pdf", "name": "x.pptx"})
    monkeypatch.setattr(worker, "buscar_video_no_drive", lambda n: {"webViewLink": "https://drive/v", "name": "x.mov",
                                                                     "size": str(200 * 1024 * 1024), "md5Checksum": "a"})
    assert worker.verificar_compliance_drive.run(cr.id, cr.nome_ficheiro_gerado) is True
    db_session.expire_all()
    r = db_session.get(ClassReport, cr.id)
    assert r.video_link == "https://drive/v" and r.slide_link == "https://drive/pdf"


def test_finalizar_ou_desmarcar_corrompido_dispara_busca(db_session, admin_user, monkeypatch):
    import app.tasks.worker as worker
    from app.services.busca_links import disparar_busca_apos_diretor

    chamados = []
    monkeypatch.setattr(worker.verificar_compliance_drive, "delay", lambda *a, **k: chamados.append(a))
    s = _cenario(db_session)
    cr = _cr(db_session, s, admin_user.id)
    idr = _idr_com_aula(db_session, s, admin_user.id, cr, status="RASCUNHO")
    assert disparar_busca_apos_diretor(db_session, idr) == 0           # ainda rascunho
    idr.status = "AGUARDANDO_VALIDACAO"
    idr.lessons[0].video_corrompido = "Sim"
    db_session.commit()
    assert disparar_busca_apos_diretor(db_session, idr) == 0           # corrompido
    idr.lessons[0].video_corrompido = "Não"
    db_session.commit()
    assert disparar_busca_apos_diretor(db_session, idr) == 1
    assert chamados == [(str(cr.id), cr.nome_ficheiro_gerado)]


def test_coordenacao_so_valida_com_os_dois_links(client, db_session, admin_user, admin_headers):
    s = _cenario(db_session)
    cr = _cr(db_session, s, admin_user.id, video_link="https://drive/v")
    r = client.patch(f"/api/v1/reports/{cr.id}/validar", headers=admin_headers)
    assert r.status_code == 400 and "PDF" in r.json()["detail"]
    cr.slide_link = "https://drive/pdf"
    db_session.commit()
    r = client.patch(f"/api/v1/reports/{cr.id}/validar", headers=admin_headers)
    assert r.status_code == 200, r.text and r.json()["status"] == "VALIDADO"


def test_chefe_nao_valida_video_corrompido(client, db_session, admin_user, admin_headers):
    s = _cenario(db_session)
    cr = _cr(db_session, s, admin_user.id)
    idr = _idr_com_aula(db_session, s, admin_user.id, cr, status="AGUARDANDO_VALIDACAO", corrompido="Sim")
    r = client.patch(f"/api/v1/image-director/{idr.id}/validar", headers=admin_headers)
    assert r.status_code == 400 and "corrompido" in r.json()["detail"]
    idr.lessons[0].video_corrompido = "Não"
    db_session.commit()
    r = client.patch(f"/api/v1/image-director/{idr.id}/validar", headers=admin_headers)
    assert r.status_code == 200, r.text


def test_reverificar_bloqueia_so_video_corrompido(client, db_session, admin_user, admin_headers, monkeypatch):
    import app.tasks.worker as worker

    monkeypatch.setattr(worker.verificar_compliance_drive, "delay", lambda *a, **k: None)
    s = _cenario(db_session)
    cr = _cr(db_session, s, admin_user.id)
    path = f"/api/v1/reports/{cr.id}/sync-individual"
    assert client.post(path, headers=admin_headers).status_code == 202   # sem diretor: a coordenação pode forçar
    _idr_com_aula(db_session, s, admin_user.id, cr, status="AGUARDANDO_VALIDACAO", corrompido="Sim")
    assert client.post(path, headers=admin_headers).status_code == 409


# ─── Canal do diretor e coleta de outros formatos ──────────────────────

def test_transmissao_sem_canal_iptv_e_aceita():
    from app.schemas.image_director_report import ImageDirectorLessonCreate

    l = ImageDirectorLessonCreate(numero_aula=1, disciplina_nome="QUÍMICA", professor_nome="Prof. Bia",
                                  transmissao_ou_gravada="Transmissão", canal_utilizado="")
    assert l.canal_utilizado is None


def _drive_falso(files):
    """Imita o service do Drive: devolve só os arquivos que passam no filtro de tipo da query."""
    class _Lista:
        def __init__(self, f):
            self.f = f

        def execute(self):
            return {"files": self.f}

    class _Files:
        def __init__(self):
            self.queries = []

        def list(self, q, **kw):
            self.queries.append(q)
            if "video/" in q:
                return _Lista([f for f in files if f["mimeType"].startswith("video/")])
            if "application/pdf" in q:
                return _Lista([f for f in files if f["mimeType"] == "application/pdf"])
            return _Lista(files)

    class _Service:
        def __init__(self):
            self.f = _Files()

        def files(self):
            return self.f

    return _Service()


def test_coleta_olha_o_tipo_e_ignora_a_extensao(monkeypatch):
    """Vale o tipo do arquivo (vídeo / PDF), não ".mp4" ou ".pdf" no nome."""
    from app.services import sync_drive

    assert sync_drive.sem_extensao("EM 2 QUIMICA 30 10 26 REACOES.mov") == "EM 2 QUIMICA 30 10 26 REACOES"
    assert sync_drive.sem_extensao("EM 2 QUIMICA 30 10 26 REACOES") == "EM 2 QUIMICA 30 10 26 REACOES"
    nome = "EM 2 QUÍMICA 30 10 26 REAÇÕES.mp4"     # nome gerado pelo sistema
    arquivos = [
        {"name": "EM 2 QUIMICA 30 10 26 REACOES", "mimeType": "video/quicktime", "webViewLink": "https://drive/video"},
        {"name": "EM 2 QUIMICA 30 10 26 REACOES", "mimeType": "application/pdf", "webViewLink": "https://drive/pdf"},
        {"name": "EM 2 QUIMICA 30 10 26 REACOES.pptx",
         "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "webViewLink": "x"},
    ]
    monkeypatch.setattr(sync_drive, "get_drive_service", lambda: _drive_falso(arquivos))
    v = sync_drive.buscar_video_no_drive(nome)
    assert v and v["webViewLink"] == "https://drive/video"     # vídeo sem ".mp4" no nome
    p = sync_drive.buscar_slide_no_drive(nome)
    assert p and p["webViewLink"] == "https://drive/pdf"       # PDF sem ".pdf" no nome


def test_coleta_nao_pega_tipo_errado_nem_outro_nome(monkeypatch):
    from app.services import sync_drive

    arquivos = [
        {"name": "EM 2 QUIMICA 30 10 26 REACOES.mp4", "mimeType": "application/pdf", "webViewLink": "pdf-com-nome-de-mp4"},
        {"name": "EM 2 QUIMICA 30 10 26 OUTRA AULA.mov", "mimeType": "video/quicktime", "webViewLink": "outra"},
    ]
    monkeypatch.setattr(sync_drive, "get_drive_service", lambda: _drive_falso(arquivos))
    assert sync_drive.buscar_video_no_drive("EM 2 QUIMICA 30 10 26 REACOES.mp4") is None   # é PDF, não vídeo
    p = sync_drive.buscar_slide_no_drive("EM 2 QUIMICA 30 10 26 REACOES.mp4")
    assert p and p["webViewLink"] == "pdf-com-nome-de-mp4"     # o tipo é PDF: vale, mesmo chamado ".mp4"


def test_link_do_youtube_do_assistente_vem_da_agenda(client, db_session, admin_headers, sample_professor_disciplina):
    """O link do YouTube do relatório da aula é o que o diretor-chefe cadastrou para o estúdio e turno."""
    s = _cenario(db_session)
    prof = sample_professor_disciplina["professor"]
    disc = sample_professor_disciplina["disciplina"]
    r = client.put(f"{AG}/transmissao-dia", json={"data": QUA.isoformat(), "itens": [
        {"turno": "manha", "estudio_id": s["e1"].id, "youtube_link": "https://youtu.be/do-chefe",
         "chave_transmissao": "abcd-1234"}]}, headers=admin_headers)
    assert r.status_code == 200, r.text
    payload = {"turma_id": str(s["t"].id), "disciplina_id": str(disc.id), "professor_id": str(prof.id),
               "data_aula": QUA.isoformat(), "turno": "Manhã", "estudio": "ESTÚDIO 1", "horario_aula": "1º Horário",
               "regular": "Sim", "tipo_aula": "Transmissão ao vivo", "conteudo_ministrado": "Reações",
               "bncc_habilidades": "EM13CNT101", "tipo_recursos_utilizados": ["Slides"], "canal_utilizado": "N/A",
               "youtube_link": "https://youtu.be/digitado-errado"}
    cr = client.post("/api/v1/reports/", json=payload, headers=admin_headers)
    assert cr.status_code == 201, cr.text
    assert cr.json()["youtube_link"] == "https://youtu.be/do-chefe"


def test_sem_canal_iptv_nao_gera_choque_de_canal(db_session, admin_user):
    """Duas aulas no mesmo horário, estúdios diferentes, ambas sem canal (N/A): não é choque."""
    from app.api.rotas_report import _verificar_choque_horario

    s = _cenario(db_session)
    outra = Turma(nome="EM 3 MANHÃ", modalidade="REGULAR", serie_modulo="3", turno="MANHÃ", nomenclatura_padrao="EM 3 MANHÃ")
    db_session.add(outra)
    db_session.commit()
    _cr(db_session, s, admin_user.id, data_aula=date(2026, 10, 28), estudio="ESTÚDIO 2", canal_utilizado="N/A",
        tipo_aula="Transmissão ao vivo", turma_id=outra.id)
    _verificar_choque_horario(db_session, date(2026, 10, 28), "ESTÚDIO 1", time(8, 30), time(9, 30),
                              canal_utilizado="N/A", tipo_aula="Transmissão ao vivo")
