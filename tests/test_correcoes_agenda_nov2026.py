"""Correções de 10/11/2026 (testes em HML): aviso repetido na edição, link/chave/professor da
gravação no relatório do diretor e o que o diretor de imagem / pedagógico consegue ver."""
from datetime import date, time

from app.core.security import create_access_token, get_password_hash
from app.models.auxiliares import Disciplina, Grade, Professor
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import ImageDirectorReport
from app.models.infraestrutura import Estudio
from app.models.turma import Turma
from app.models.user import User

TERCA = date(2026, 11, 10)  # dia_semana 1
AG = "/api/v1/agenda-estudios"
CTX = "/api/v1/image-director/lookup/contexto-estudio"


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
    """Igual ao caso de HML: EM 2 TI com Geografia no Estúdio 2 (10:50–11:50) e gravação no Estúdio 4."""
    e2 = Estudio(nome="ESTÚDIO 2", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    e4 = Estudio(nome="ESTÚDIO 4", horario_inicio=time(6, 0), horario_fim=time(23, 0))
    t = Turma(nome="2ª Série Integral", modalidade="REGULAR", serie_modulo="2ª Série", turno="INTEGRAL",
              nomenclatura_padrao="EM 2 TI")
    geo = Disciplina(nome="GEOGRAFIA")
    fil = Disciplina(nome="FILOSOFIA")
    prof = Professor(nome="RAPHAELL MARQUES DA SILVA")
    db.add_all([e2, e4, t, geo, fil, prof])
    db.flush()
    db.add_all([
        Grade(turma_id=t.id, disciplina_id=geo.id, estudio_id=e2.id, dia_semana=1,
              horario_inicio=time(10, 50), horario_fim=time(11, 50)),
        # aula da tarde no Estúdio 4: o contexto da manhã não pode pegar esta
        Grade(turma_id=t.id, disciplina_id=fil.id, estudio_id=e4.id, dia_semana=1,
              horario_inicio=time(14, 0), horario_fim=time(15, 0)),
    ])
    db.commit()
    return dict(e2=e2.id, e4=e4.id, t=str(t.id), prof=str(prof.id))


def _gravacao(s, **extra):
    return {"data": TERCA.isoformat(), "estudio_id": s["e4"], "horario_inicio": "11:20", "horario_fim": "12:20",
            "tipo": "GRAVACAO", "titulo": "| 2ª SÉRIE INTEGRAL | MATEMÁTICA", "turma_id": s["t"],
            "professor": "RAPHAELL MARQUES DA SILVA", "chamado": "19031",
            "chamado_link": "https://chamados.exemplo/19031",
            "youtube_link": "https://youtube.com/live/HNh0TTKJBJk",
            "chave_transmissao": "h9y2-2cy7-47ck-2e5a-311x", **extra}


def test_gravacao_nao_avisa_aula_da_turma_e_edicao_sem_mudanca_nao_repete_aviso(client, db_session, admin_headers):
    s = _cenario(db_session)
    # A turma tem Geografia no Estúdio 2 das 10:50 às 11:50, mas na gravação ela não vai ao estúdio
    r = client.post(f"{AG}/agendamentos", json=_gravacao(s), headers=admin_headers)
    assert r.status_code == 201, r.text
    ag = r.json()
    assert ag["chamado_link"] == "https://chamados.exemplo/19031"
    assert ag["youtube_link"] == "https://youtube.com/live/HNh0TTKJBJk"

    # Aviso que continua valendo (relatório/professor etc.): força um aviso com outro agendamento do professor
    outro = client.post(f"{AG}/agendamentos", json={**_gravacao(s), "estudio_id": s["e2"], "horario_inicio": "12:40",
                                                     "horario_fim": "13:40", "youtube_link": None,
                                                     "chave_transmissao": None}, headers=admin_headers)
    assert outro.status_code == 201, outro.text
    corpo = {**_gravacao(s), "horario_inicio": "12:30", "horario_fim": "13:30"}
    r = client.put(f"{AG}/agendamentos/{ag['id']}", json=corpo, headers=admin_headers)
    assert r.status_code == 409 and any("já está agendado" in a for a in r.json()["detail"]["avisos"])
    r = client.put(f"{AG}/agendamentos/{ag['id']}", json={**corpo, "confirmar_avisos": True}, headers=admin_headers)
    assert r.status_code == 200, r.text

    # Editar só o título/observação: o aviso já foi aceito, não pede de novo
    r = client.put(f"{AG}/agendamentos/{ag['id']}", json={**corpo, "descricao": "mudou só a observação"},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    # Mudar o horário volta a checar
    r = client.put(f"{AG}/agendamentos/{ag['id']}", json={**corpo, "horario_inicio": "12:35", "horario_fim": "13:35"},
                   headers=admin_headers)
    assert r.status_code == 409


def test_link_chave_e_professor_da_gravacao_chegam_ao_diretor(client, db_session, admin_headers):
    s = _cenario(db_session)
    hd, d = _user(db_session, "diretor_imagem", "ana@t.com", diretor=True)
    ho, _ = _user(db_session, "diretor_imagem", "beto@t.com", diretor=True)
    ag = client.post(f"{AG}/agendamentos", json=_gravacao(s), headers=admin_headers).json()
    client.put(f"{AG}/escala-dia", json={"data": TERCA.isoformat(), "turno": "manha", "estudio_id": s["e4"],
                                         "diretor_imagem_id": str(d.id)}, headers=admin_headers)

    # Formulário do diretor aberto pela grade (estudio-da-aula com o agendamento)
    q = {"turma_id": s["t"], "data": TERCA.isoformat(), "inicio": "11:20", "agendamento_id": ag["id"]}
    r = client.get(f"{AG}/estudio-da-aula", params=q, headers=hd).json()
    assert r["encontrado"] and r["estudio"] == "ESTÚDIO 4"
    assert r["youtube_link"] == "https://youtube.com/live/HNh0TTKJBJk"
    assert r["chave_transmissao"] == "h9y2-2cy7-47ck-2e5a-311x"
    assert r["professor"] == "RAPHAELL MARQUES DA SILVA"
    # diretor não escalado: link sim, chave não
    assert client.get(f"{AG}/estudio-da-aula", params=q, headers=ho).json()["chave_transmissao"] is None

    # Formulário por Data + Turno + Estúdio (contexto-estudio)
    ctx = client.get(CTX, params={"data": TERCA.isoformat(), "turno": "Manhã", "estudio": "ESTÚDIO 4"},
                     headers=hd).json()
    assert ctx["youtube_link"] == "https://youtube.com/live/HNh0TTKJBJk" and ctx["link_da_agenda"] is True
    assert ctx["chave_transmissao"] == "h9y2-2cy7-47ck-2e5a-311x" and ctx["chave_da_agenda"] is True
    assert ctx["turma_id"] == s["t"]
    assert ctx["professor_nome"] == "RAPHAELL MARQUES DA SILVA" and ctx["professor_id"] == s["prof"]
    assert ctx["horario_aula"] == "11:20 às 12:20"
    ctx_outro = client.get(CTX, params={"data": TERCA.isoformat(), "turno": "Manhã", "estudio": "ESTÚDIO 4"},
                           headers=ho).json()
    assert ctx_outro["chave_transmissao"] is None

    # À tarde o Estúdio 4 tem Filosofia da grade: não herda a gravação da manhã
    tarde = client.get(CTX, params={"data": TERCA.isoformat(), "turno": "Tarde", "estudio": "ESTÚDIO 4"},
                       headers=hd).json()
    assert tarde["youtube_link"] is None and tarde["chave_transmissao"] is None
    assert tarde["disciplina_nome"] == "FILOSOFIA" and tarde["horario_aula"] == "14:00 às 15:00"


def test_registro_antigo_com_youtube_no_campo_do_chamado(client, db_session, admin_headers):
    s = _cenario(db_session)
    corpo = _gravacao(s, youtube_link=None, chamado_link="https://youtube.com/live/antigo")
    ag = client.post(f"{AG}/agendamentos", json=corpo, headers=admin_headers).json()
    assert ag["youtube_link"] == "https://youtube.com/live/antigo"
    ctx = client.get(CTX, params={"data": TERCA.isoformat(), "turno": "Manhã", "estudio": "ESTÚDIO 4"},
                     headers=admin_headers).json()
    assert ctx["youtube_link"] == "https://youtube.com/live/antigo"


def test_chave_nao_vaza_para_quem_so_consulta_nem_na_grade_por_estudio(client, db_session, admin_headers):
    s = _cenario(db_session)
    client.post(f"{AG}/agendamentos", json=_gravacao(s), headers=admin_headers)
    coord, _ = _user(db_session, "coordenador", "coord@t.com")
    hd, _ = _user(db_session, "diretor_imagem", "ana@t.com", diretor=True)

    dia = client.get(f"{AG}/dia", params={"data": TERCA.isoformat()}, headers=coord).json()
    registros = [i["registro"] for t in dia["turnos"] for c in t["estudios"] for i in c["itens"] if i.get("registro")]
    assert registros and all("chave_transmissao" not in r for r in registros)
    lista = client.get(f"{AG}/agendamentos", params={"data_inicio": TERCA.isoformat(), "data_fim": TERCA.isoformat()},
                       headers=coord).json()["items"]
    assert lista and all("chave_transmissao" not in a for a in lista)
    # quem edita a Agenda continua vendo
    lista_adm = client.get(f"{AG}/agendamentos", params={"data_inicio": TERCA.isoformat(),
                                                          "data_fim": TERCA.isoformat()}, headers=admin_headers).json()
    assert lista_adm["items"][0]["chave_transmissao"] == "h9y2-2cy7-47ck-2e5a-311x"

    # Grade por estúdio: sem chave para ninguém; diretor de imagem usa a própria escala
    url = f"/api/v1/turmas/grade-estudio/{s['e4']}"
    params = {"data_inicio": TERCA.isoformat(), "data_fim": TERCA.isoformat()}
    itens = client.get(url, params=params, headers=admin_headers).json()
    assert any(i.get("agendamento_id") for i in itens)
    assert all("chave_transmissao" not in i for i in itens)
    assert client.get(url, params=params, headers=hd).status_code == 403


def test_diretor_nao_ve_conferencia_do_relatorio_de_outro(client, db_session, admin_headers):
    _cenario(db_session)
    ha, a = _user(db_session, "diretor_imagem", "ana@t.com", diretor=True)
    hb, _ = _user(db_session, "diretor_imagem", "beto@t.com", diretor=True)
    rep = ImageDirectorReport(created_by=a.user_id, diretor_imagem_id=a.id, data_relatorio=TERCA, turno="Manhã", estudio="ESTÚDIO 4",
                              status="RASCUNHO")
    db_session.add(rep)
    db_session.commit()
    url = f"/api/v1/image-director/{rep.id}/conferencia-par"
    assert client.get(url, headers=ha).status_code == 200
    assert client.get(url, headers=hb).status_code == 403
