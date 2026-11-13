"""Casamento assistente x diretor de imagem, estúdio da Agenda, escala do diretor, link/chave."""
import importlib.util
import os
import uuid
from datetime import date, time

from app.core.security import create_access_token, get_password_hash
from app.models.auxiliares import Disciplina, Grade
from app.models.class_report import ClassReport
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import ImageDirectorReport
from app.models.infraestrutura import Estudio
from app.models.turma import Turma
from app.models.user import User
from app.services.audit_export import _build_pairings
from app.services.image_director_associacao import vincular_image_director_ao_class_report

TERCA = date(2026, 10, 13)
AG = "/api/v1/agenda-estudios"


def _user(db, role, email, diretor=False):
    u = User(email=email, full_name=email, role=role, hashed_password=get_password_hash("x"), email_confirmed=True)
    db.add(u); db.flush()
    d = None
    if diretor:
        d = DiretorImagem(nome=email.split("@")[0].upper(), user_id=u.id, is_active=True)
        db.add(d)
    db.commit()
    h = {"Authorization": f"Bearer {create_access_token(data={'sub': u.email, 'role': u.role, 'user_id': str(u.id)})}"}
    return h, d


def _cenario(db):
    e4 = Estudio(nome="ESTÚDIO 4", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    e7 = Estudio(nome="ESTÚDIO 7", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    t = Turma(nome="EM 3 MANHÃ", modalidade="REGULAR", serie_modulo="3", turno="MANHÃ", nomenclatura_padrao="EM 3 MANHÃ")
    d = Disciplina(nome="FILOSOFIA")
    db.add_all([e4, e7, t, d]); db.flush()
    g = Grade(turma_id=t.id, disciplina_id=d.id, estudio_id=e4.id, dia_semana=1,
              horario_inicio=time(10, 20), horario_fim=time(11, 20))
    db.add(g); db.commit()
    return dict(e4=e4, e7=e7, t=t, d=d, g=g)


def _cr(db, s, estudio, turno="Manhã"):
    r = ClassReport(created_by=uuid.uuid4(), status="AGUARDANDO_VALIDACAO", data_aula=TERCA, turno=turno, estudio=estudio,
                    turma_id=s["t"].id, disciplina_id=s["d"].id, horario_aula="4º Horário",
                    start_time=time(10, 20), end_time=time(11, 20), tipo_aula="Transmissão ao vivo",
                    canal_utilizado="1", conteudo_ministrado="X", status_compliance="Pendente")
    db.add(r); db.commit()
    return r


def _idr(client, s, h, diretor, estudio, turno="Manhã", class_report_id=None):
    p = {"diretor_imagem_id": str(diretor.id), "data_relatorio": TERCA.isoformat(), "turno": turno, "estudio": estudio,
         "turma_id": str(s["t"].id), "disciplina_id": str(s["d"].id), "disciplina_nome": "FILOSOFIA",
         "professor_nome_externo": "Prof. Ana", "horario_aula": "10:20 às 11:20", "origem": "grade"}
    if class_report_id:
        p["class_report_id"] = str(class_report_id)
    r = client.post("/api/v1/image-director/", json=p, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_aula_remanejada_estudio_e_diretor_da_agenda(client, db_session, admin_headers):
    s = _cenario(db_session)
    _hd, dir7 = _user(db_session, "diretor_imagem", "joao@t.com", diretor=True)
    client.post(f"{AG}/aulas/remanejar", json={"data": TERCA.isoformat(), "grade_id": str(s["g"].id),
                                              "estudio_destino_id": s["e7"].id}, headers=admin_headers)
    client.put(f"{AG}/escala-dia", json={"data": TERCA.isoformat(), "turno": "manha", "estudio_id": s["e7"].id,
                                         "diretor_imagem_id": str(dir7.id)}, headers=admin_headers)
    r = client.get(f"{AG}/estudio-da-aula", params={"turma_id": str(s["t"].id), "data": TERCA.isoformat(),
                                                    "horario": "4º Horário", "turno": "Manhã"}, headers=admin_headers).json()
    assert r["estudio"] == "ESTÚDIO 7" and r["remanejada"] and r["diretor_nome"] == "JOAO"
    assert r["diretor_imagem_id"] == str(dir7.id) and r["antecipada"] is False


def test_liga_mesmo_com_grafia_diferente_e_consolidado_pareia(client, db_session):
    s = _cenario(db_session)
    h, d = _user(db_session, "diretor_imagem", "maria@t.com", diretor=True)
    idr = _idr(client, s, h, d, "Estúdio 04", turno="MANHÃ")       # diretor primeiro, outra grafia
    cr = _cr(db_session, s, "ESTÚDIO 4", turno="Manhã")
    vincular_image_director_ao_class_report(db_session, cr); db_session.commit()
    assert db_session.get(ImageDirectorReport, uuid.UUID(idr["id"])).class_report_id == cr.id
    rows, _ = _build_pairings(db_session.query(ClassReport).all(), db_session.query(ImageDirectorReport).all())
    assert len(rows) == 1 and rows[0][0] and rows[0][1]


def test_conferencia_do_par_aponta_estudio_diferente(client, db_session, admin_headers):
    s = _cenario(db_session)
    h, d = _user(db_session, "diretor_imagem", "pedro@t.com", diretor=True)
    cr = _cr(db_session, s, "ESTÚDIO 7")
    idr = _idr(client, s, h, d, "ESTÚDIO 4", class_report_id=cr.id)
    lado_diretor = client.get(f"/api/v1/image-director/{idr['id']}/conferencia-par", headers=admin_headers).json()
    lado_assist = client.get(f"/api/v1/reports/{cr.id}/conferencia-par", headers=admin_headers).json()
    assert lado_diretor["tem_par"] and any("Estúdio" in m for m in lado_diretor["divergencias"])
    assert lado_assist["tem_par"] and any("Estúdio" in m for m in lado_assist["divergencias"])
    # par que bate: sem divergência
    cr2 = _cr(db_session, s, "ESTÚDIO 4")
    assert client.get(f"/api/v1/reports/{cr2.id}/conferencia-par", headers=admin_headers).json()["divergencias"] == []


def test_minha_escala_e_link_chave_so_para_quem_pode(client, db_session, admin_headers):
    s = _cenario(db_session)
    hd, d = _user(db_session, "diretor_imagem", "ana@t.com", diretor=True)
    ho, outro = _user(db_session, "diretor_imagem", "beto@t.com", diretor=True)
    hg, _ = _user(db_session, "gestor", "gestor@t.com")
    client.put(f"{AG}/escala-dia", json={"data": TERCA.isoformat(), "turno": "manha", "estudio_id": s["e4"].id,
                                         "diretor_imagem_id": str(d.id), "youtube_link": "https://youtu.be/abc",
                                         "chave_transmissao": "xxxx-yyyy"}, headers=admin_headers)
    minha = client.get(f"{AG}/minha-escala", params={"data": TERCA.isoformat()}, headers=hd).json()
    assert [t["turno"] for t in minha["turnos"]] == ["manha"]
    col = minha["turnos"][0]["estudios"][0]
    assert col["estudio_nome"] == "ESTÚDIO 4" and col["youtube_link"] == "https://youtu.be/abc"
    assert col["chave_transmissao"] == "xxxx-yyyy" and [i["titulo"] for i in col["itens"]] == ["FILOSOFIA"]
    # outro diretor não vê a escala/chave de ninguém
    assert client.get(f"{AG}/minha-escala", params={"data": TERCA.isoformat()}, headers=ho).json()["turnos"] == []
    # gestor (só consulta) não recebe link nem chave
    esc = client.get(f"{AG}/escala-dia", params={"data": TERCA.isoformat()}, headers=hg).json()
    assert "chave_transmissao" not in esc[0]
    dia = client.get(f"{AG}/dia", params={"data": TERCA.isoformat()}, headers=hg).json()
    dirs = [c["diretor"] for t in dia["turnos"] for c in t["estudios"] if c.get("diretor")]
    assert dirs and all("chave_transmissao" not in x for x in dirs)
    # assistente não acessa a escala do diretor
    assert client.get(f"{AG}/minha-escala", headers=_user(db_session, "assistente", "as@t.com")[0]).status_code == 403
    # ao copiar o dia, vão só os diretores: link e chave mudam todo dia
    client.post(f"{AG}/escala-dia/copiar", json={"de_data": TERCA.isoformat(), "para_datas": ["2026-10-20"]},
                headers=admin_headers)
    copia = client.get(f"{AG}/escala-dia", params={"data": "2026-10-20"}, headers=admin_headers).json()[0]
    assert copia["diretor_imagem_id"] == str(d.id)
    assert copia["chave_transmissao"] is None and copia["youtube_link"] is None


def test_link_e_chave_do_dia_por_estudio_e_turno(client, db_session, admin_headers):
    """Link/chave valem para todas as aulas do estúdio no turno, com ou sem diretor, e os relatórios puxam."""
    s = _cenario(db_session)
    hd, d = _user(db_session, "diretor_imagem", "ana@t.com", diretor=True)
    ho, outro = _user(db_session, "diretor_imagem", "beto@t.com", diretor=True)
    ha, _ = _user(db_session, "assistente", "as@t.com")
    # estúdio sem diretor: o link e a chave podem ser informados mesmo assim
    r = client.put(f"{AG}/transmissao-dia", json={"data": TERCA.isoformat(), "itens": [
        {"turno": "manha", "estudio_id": s["e4"].id, "youtube_link": "https://youtu.be/dia13", "chave_transmissao": "k-13"},
        {"turno": "tarde", "estudio_id": s["e4"].id, "youtube_link": "", "chave_transmissao": ""},
    ]}, headers=admin_headers)
    assert r.status_code == 200, r.text
    lista = client.get(f"{AG}/transmissao-dia", params={"data": TERCA.isoformat()}, headers=admin_headers).json()
    assert lista == [{"turno": "manha", "estudio_id": s["e4"].id, "youtube_link": "https://youtu.be/dia13",
                      "chave_transmissao": "k-13"}]
    assert client.get(f"{AG}/transmissao-dia", params={"data": TERCA.isoformat()}, headers=ha).status_code == 403
    q = {"turma_id": str(s["t"].id), "data": TERCA.isoformat(), "inicio": "10:20"}
    # assistente: puxa o link, não a chave
    a = client.get(f"{AG}/estudio-da-aula", params=q, headers=ha).json()
    assert a["youtube_link"] == "https://youtu.be/dia13" and a["chave_transmissao"] is None
    # escalar o diretor depois não apaga o link/chave
    client.put(f"{AG}/escala-dia", json={"data": TERCA.isoformat(), "turno": "manha", "estudio_id": s["e4"].id,
                                         "diretor_imagem_id": str(d.id)}, headers=admin_headers)
    assert client.get(f"{AG}/estudio-da-aula", params=q, headers=hd).json()["chave_transmissao"] == "k-13"
    assert client.get(f"{AG}/estudio-da-aula", params=q, headers=ho).json()["chave_transmissao"] is None
    ctx = client.get("/api/v1/image-director/lookup/contexto-estudio",
                     params={"data": TERCA.isoformat(), "turno": "Manhã", "estudio": "ESTÚDIO 4"}, headers=hd).json()
    assert ctx["youtube_link"] == "https://youtu.be/dia13" and ctx["chave_transmissao"] == "k-13"
    ctx2 = client.get("/api/v1/image-director/lookup/contexto-estudio",
                      params={"data": TERCA.isoformat(), "turno": "Manhã", "estudio": "ESTÚDIO 4"}, headers=ho).json()
    assert ctx2["youtube_link"] == "https://youtu.be/dia13" and ctx2["chave_transmissao"] is None
    # remanejada: a aula puxa o link do estúdio de destino
    client.put(f"{AG}/transmissao-dia", json={"data": TERCA.isoformat(), "itens": [
        {"turno": "manha", "estudio_id": s["e7"].id, "youtube_link": "https://youtu.be/e7", "chave_transmissao": "k-7"}]},
        headers=admin_headers)
    client.post(f"{AG}/aulas/remanejar", json={"data": TERCA.isoformat(), "grade_id": str(s["g"].id),
                                              "estudio_destino_id": s["e7"].id}, headers=admin_headers)
    assert client.get(f"{AG}/estudio-da-aula", params=q, headers=ha).json()["youtube_link"] == "https://youtu.be/e7"
    # tirar o diretor mantém o link; apagar link e chave sem diretor remove a linha
    client.put(f"{AG}/escala-dia", json={"data": TERCA.isoformat(), "turno": "manha", "estudio_id": s["e4"].id,
                                         "diretor_imagem_id": None}, headers=admin_headers)
    esc = client.get(f"{AG}/escala-dia", params={"data": TERCA.isoformat()}, headers=admin_headers).json()
    e4 = [x for x in esc if x["estudio_id"] == s["e4"].id][0]
    assert e4["diretor_imagem_id"] is None and e4["youtube_link"] == "https://youtu.be/dia13"
    client.put(f"{AG}/transmissao-dia", json={"data": TERCA.isoformat(), "itens": [
        {"turno": "manha", "estudio_id": s["e4"].id, "youtube_link": "", "chave_transmissao": ""}]}, headers=admin_headers)
    esc = client.get(f"{AG}/escala-dia", params={"data": TERCA.isoformat()}, headers=admin_headers).json()
    assert [x["estudio_id"] for x in esc] == [s["e7"].id]
    # o dia da agenda mostra a transmissão só para quem edita
    hg, _ = _user(db_session, "gestor", "g@t.com")
    dia = client.get(f"{AG}/dia", params={"data": TERCA.isoformat()}, headers=hg).json()
    assert all("transmissao" not in c for t in dia["turnos"] for c in t["estudios"])


def test_semana_da_turma_e_aula_antecipada(client, db_session, admin_headers):
    s = _cenario(db_session)
    client.post(f"{AG}/aulas/remanejar", json={"data": TERCA.isoformat(), "grade_id": str(s["g"].id),
                                              "estudio_destino_id": s["e7"].id}, headers=admin_headers)
    r = client.post(f"{AG}/agendamentos", json={"data": TERCA.isoformat(), "estudio_id": s["e7"].id,
                                                "horario_inicio": "14:00", "horario_fim": "15:00",
                                                "tipo": "GRAVACAO_ANTECIPADA", "titulo": "Filosofia (aula de 20/10)",
                                                "turma_id": str(s["t"].id), "confirmar_avisos": True}, headers=admin_headers)
    assert r.status_code == 201, r.text
    sem = client.get(f"{AG}/semana-turma", params={"turma_id": str(s["t"].id), "data_inicio": "2026-10-12",
                                                   "data_fim": "2026-10-18"}, headers=admin_headers).json()
    assert sem["ocorrencias"][0]["estudio_nome"] == "ESTÚDIO 7" and sem["ocorrencias"][0]["tipo"] == "AULA_REMANEJADA"
    assert [e["tipo"] for e in sem["extras"]] == ["GRAVACAO_ANTECIPADA"]
    ant = client.get(f"{AG}/estudio-da-aula", params={"turma_id": str(s["t"].id), "data": TERCA.isoformat(),
                                                      "inicio": "14:00"}, headers=admin_headers).json()
    assert ant["encontrado"] and ant["antecipada"] is True and ant["estudio"] == "ESTÚDIO 7"
    # Antecipada marcada no mesmo horário de uma aula da grade: aberta pela lista da grade, vale o agendamento
    r2 = client.post(f"{AG}/agendamentos", json={"data": TERCA.isoformat(), "estudio_id": s["e4"].id,
                                                 "horario_inicio": "10:20", "horario_fim": "11:20",
                                                 "tipo": "REPOSICAO", "titulo": "Reposição", "turma_id": str(s["t"].id),
                                                 "confirmar_avisos": True}, headers=admin_headers)
    assert r2.status_code == 201, r2.text
    rep = client.get(f"{AG}/estudio-da-aula", params={"turma_id": str(s["t"].id), "data": TERCA.isoformat(),
                                                      "horario": "10:20 às 11:20", "agendamento_id": r2.json()["id"]},
                     headers=admin_headers).json()
    # Reunião 26/10: reposição é uma gravação (o diretor registra como "Aula gravada")
    assert rep["tipo_agenda"] == "REPOSICAO" and rep["estudio"] == "ESTÚDIO 4" and rep["reposicao"] is True


def test_script_numeracao_antiga(db_session):
    spec = importlib.util.spec_from_file_location(
        "corrigir", os.path.join(os.path.dirname(__file__), "..", "scripts", "corrigir_numeracao_horario_diretor.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    t = Turma(nome="EPT ESTUDIO 2", modalidade="TECNICO", serie_modulo="-", turno="INTEGRAL", nomenclatura_padrao="EPT ESTUDIO 2 TI")
    d = Disciplina(nome="FARMACOLOGIA")
    db_session.add_all([t, d]); db_session.flush()
    for ini, fim in [((10, 50), (11, 50)), ((12, 50), (13, 50))]:
        db_session.add(Grade(turma_id=t.id, disciplina_id=d.id, dia_semana=4, horario_inicio=time(*ini), horario_fim=time(*fim)))
    di = DiretorImagem(nome="X", is_active=True); db_session.add(di); db_session.flush()
    base = dict(created_by=uuid.uuid4(), diretor_imagem_id=di.id, data_relatorio=date(2026, 10, 2), turno="Manhã",
                estudio="ESTÚDIO 2", turma_id=t.id, origem="grade", status="AGUARDANDO_VALIDACAO")
    antigo = ImageDirectorReport(**base, horario_aula="1º Horário", start_time=time(10, 50), end_time=time(11, 50))
    certo = ImageDirectorReport(**{**base, "turno": "Tarde"}, horario_aula="5º Horário", start_time=time(12, 50), end_time=time(13, 50))
    db_session.add_all([antigo, certo]); db_session.commit()
    achados = mod.encontrar(db_session, date(2026, 10, 1), date(2026, 10, 31))
    assert [(r.id, g, o) for r, g, o in achados] == [(antigo.id, 1, 4)]


def test_relatorio_do_diretor_usa_link_e_chave_do_chefe(client, db_session, admin_headers):
    """O diretor não troca o link/chave informados pelo diretor-chefe: o relatório grava os da Agenda."""
    s = _cenario(db_session)
    hd, d = _user(db_session, "diretor_imagem", "ana@t.com", diretor=True)
    client.put(f"{AG}/transmissao-dia", json={"data": TERCA.isoformat(), "itens": [
        {"turno": "manha", "estudio_id": s["e4"].id, "youtube_link": "https://youtu.be/chefe", "chave_transmissao": "k-chefe"}]},
        headers=admin_headers)
    ctx = client.get("/api/v1/image-director/lookup/contexto-estudio",
                     params={"data": TERCA.isoformat(), "turno": "Manhã", "estudio": "Estúdio 04"}, headers=admin_headers).json()
    assert ctx["link_da_agenda"] is True and ctx["chave_da_agenda"] is True
    p = {"diretor_imagem_id": str(d.id), "data_relatorio": TERCA.isoformat(), "turno": "Manhã", "estudio": "Estúdio 04",
         "turma_id": str(s["t"].id), "disciplina_id": str(s["d"].id), "disciplina_nome": "FILOSOFIA",
         "professor_nome_externo": "Prof. Ana", "horario_aula": "10:20 às 11:20", "origem": "grade",
         "youtube_link": "https://youtu.be/outro", "chave_transmissao": "trocada"}
    r = client.post("/api/v1/image-director/", json=p, headers=hd)
    assert r.status_code == 201, r.text
    assert r.json()["youtube_link"] == "https://youtu.be/chefe" and r.json()["chave_transmissao"] == "k-chefe"
    u = client.put(f"/api/v1/image-director/{r.json()['id']}", json={"youtube_link": "https://youtu.be/x"}, headers=hd)
    assert u.json()["youtube_link"] == "https://youtu.be/chefe"


def test_dados_do_chefe_vao_para_os_relatorios(client, db_session, admin_headers):
    """Horário, canal, diretor, antecipação e chamado definidos na Agenda chegam aos relatórios."""
    from app.models.infraestrutura import CanalIptvModel
    s = _cenario(db_session)
    canal = CanalIptvModel(nome="SEDUC PI 3", numero=3, ativo=True)
    db_session.add(canal); db_session.commit()
    s["g"].canal_iptv_id = canal.id; db_session.commit()
    hd, d = _user(db_session, "diretor_imagem", "ana@t.com", diretor=True)
    client.put(f"{AG}/escala-dia", json={"data": TERCA.isoformat(), "turno": "manha", "estudio_id": s["e4"].id,
                                         "diretor_imagem_id": str(d.id)}, headers=admin_headers)
    q = {"turma_id": str(s["t"].id), "data": TERCA.isoformat(), "horario": "4º Horário"}
    r = client.get(f"{AG}/estudio-da-aula", params={**q, "horario": "10:20 às 11:20"}, headers=admin_headers).json()
    assert r["canal"] == "SEDUC PI 3" and r["horario_faixa"] == "10:20 às 11:20" and r["turno"] == "manha"
    assert r["diretor_nome"] == "ANA" and r["disciplina"] == "FILOSOFIA" and r["tipo_agenda"] is None
    # gravação antecipada marcada pelo chefe: solicitante, referência e chamado vão para o relatório do diretor
    a = client.post(f"{AG}/agendamentos", json={"data": TERCA.isoformat(), "estudio_id": s["e4"].id,
                                                 "horario_inicio": "14:00", "horario_fim": "15:00",
                                                 "tipo": "GRAVACAO_ANTECIPADA", "titulo": "Filosofia (aula de 20/10)",
                                                 "turma_id": str(s["t"].id), "chamado": "18097",
                                                 "solicitante_antecipacao": "SEDUC", "data_referencia": "2026-10-20",
                                                 "canal_iptv_id": canal.id, "confirmar_avisos": True}, headers=admin_headers)
    assert a.status_code == 201, a.text
    ag = client.get(f"{AG}/estudio-da-aula", params={"turma_id": str(s["t"].id), "data": TERCA.isoformat(),
                                                      "inicio": "14:00"}, headers=admin_headers).json()
    assert ag["antecipada"] and ag["chamado"] == "18097" and ag["canal"] == "SEDUC PI 3"
    p = {"diretor_imagem_id": str(d.id), "data_relatorio": TERCA.isoformat(), "turno": "Tarde", "estudio": "ESTÚDIO 4",
         "turma_id": str(s["t"].id), "disciplina_nome": "FILOSOFIA", "professor_nome_externo": "Prof. Ana",
         "horario_aula": "14:00 às 15:00", "origem": "grade"}
    idr = client.post("/api/v1/image-director/", json=p, headers=hd)
    assert idr.status_code == 201, idr.text
    j = idr.json()
    assert j["solicitante_antecipacao"] == "SEDUC" and j["data_referencia"] == "2026-10-20" and j["ticket_number"] == "18097"
