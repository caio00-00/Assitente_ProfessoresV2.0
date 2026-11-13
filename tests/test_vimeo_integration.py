"""
Canal Educação v3.0 — Tests: Integração Vimeo Sync.
Testa a normalização de nome de arquivo usada para casar o link do Vimeo
(POST /api/v1/external/vimeo-link) com os relatórios de aula, e a semântica
de resposta do endpoint (200/404/409/403).
"""

import os
from datetime import date

import pytest

# Chave da API externa precisa estar configurada ANTES de validar o token.
os.environ["EXTERNAL_API_KEY"] = "test-external-key"

from app.utils.text_utils import normalizar_para_match as _normalizar_nome


class TestNormalizarNome:
    def test_remove_extensao_mp4(self):
        assert _normalizar_nome("AULA 02 ECONOMIA.mp4") == _normalizar_nome("AULA 02 ECONOMIA")

    def test_ignora_caixa(self):
        assert _normalizar_nome("Aula 02 Economia") == _normalizar_nome("AULA 02 ECONOMIA")

    def test_remove_acentos(self):
        # "SEGMENTAÇÃO" vs "SEGMENTACAO" devem casar
        assert _normalizar_nome("EM 1 TI FILOSOFIA 04 12 26 ÉTICA") == \
               _normalizar_nome("EM 1 TI FILOSOFIA 04 12 26 ETICA")

    def test_ignora_separadores_e_espacos(self):
        assert _normalizar_nome("AULA 02 - ECONOMIA_CRIATIVA") == \
               _normalizar_nome("AULA02ECONOMIACRIATIVA")

    def test_nomes_diferentes_nao_casam(self):
        assert _normalizar_nome("AULA 01 HISTORIA") != _normalizar_nome("AULA 02 HISTORIA")

    def test_vazio(self):
        assert _normalizar_nome("") == ""
        assert _normalizar_nome(".mp4") == ""

    def test_caso_real_vimeo_sync(self):
        # Nome vindo do Drive (Vimeo Sync) vs nome gerado pelo Assistente
        do_drive = "AULA 02 ECONOMIA CRIATIVA SEGMENTAÇÃO DE MERCADO.mp4"
        do_assistente = "AULA 02 ECONOMIA CRIATIVA SEGMENTACAO DE MERCADO.mp4"
        assert _normalizar_nome(do_drive) == _normalizar_nome(do_assistente)


# ─── Endpoint POST /api/v1/external/vimeo-link ───────────────────────────────
# O fixture `client` (TestClient) está quebrado neste venv por incompatibilidade
# httpx/starlette, então testamos a função do endpoint diretamente sobre uma
# sessão SQLite (mesma lógica de casamento e os mesmos códigos 200/404/409/422).

from fastapi import HTTPException


class _FakeClient:
    host = "127.0.0.1"


class _FakeRequest:
    def __init__(self):
        self.headers = {}
        self.client = _FakeClient()


@pytest.fixture(autouse=True)
def _refresh_settings_cache():
    """Garante que EXTERNAL_API_KEY do ambiente seja lido pelo settings cacheado."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _criar_report(db_session, turma, disc, user, nome_ficheiro,
                  vimeo_link=None, video_link=None):
    from app.models.class_report import ClassReport

    report = ClassReport(
        created_by=user.id,
        status="FINALIZADO",
        data_aula=date(2026, 6, 1),
        turno="Manhã",
        estudio="Estúdio 01",
        turma_id=turma.id,
        disciplina_id=disc.id,
        horario_aula="07:30 - 08:30",
        regular="Sim",
        tipo_aula="Transmissão ao vivo",
        canal_utilizado="1",
        conteudo_ministrado="Conteúdo de teste",
        nome_ficheiro_gerado=nome_ficheiro,
        vimeo_link=vimeo_link,
        video_link=video_link,
    )
    db_session.add(report)
    db_session.commit()
    db_session.refresh(report)
    return report


def _call(db_session, nome, vimeo_url="https://vimeo.com/123456789", drive_url=None):
    from app.api.rotas_externas import receber_vimeo_link
    from app.schemas.external import VimeoLinkInput

    payload = VimeoLinkInput(nome_ficheiro=nome, vimeo_url=vimeo_url, drive_url=drive_url)
    return receber_vimeo_link(_FakeRequest(), payload, db_session, "test-external-key")


class TestVimeoLinkAuth:
    def test_token_invalido_403(self):
        from app.api.deps import verify_external_token
        from app.core.config import get_settings
        get_settings.cache_clear()
        with pytest.raises(HTTPException) as exc:
            verify_external_token(x_api_key="errada")
        assert exc.value.status_code == 403

    def test_token_valido_ok(self):
        from app.api.deps import verify_external_token
        from app.core.config import get_settings
        get_settings.cache_clear()
        assert verify_external_token(x_api_key="test-external-key") == "test-external-key"


class TestVimeoLinkEndpoint:
    def test_nome_existente_sem_vinculo_200(
        self, db_session, sample_turma, sample_professor_disciplina, admin_user
    ):
        disc = sample_professor_disciplina["disciplina"]
        _criar_report(db_session, sample_turma, disc, admin_user,
                      "AULA 10 MATEMATICA FUNCOES.mp4")
        resp = _call(db_session, "AULA 10 MATEMATICA FUNCOES.mp4",
                     drive_url="https://drive.google.com/file/d/XYZ/view")
        assert resp.status == "vinculado"
        assert resp.updated == 1
        assert resp.drive_updated == 1

    def test_casamento_normalizado_acentos_200(
        self, db_session, sample_turma, sample_professor_disciplina, admin_user
    ):
        disc = sample_professor_disciplina["disciplina"]
        # Report com acento; payload sem acento → deve casar.
        _criar_report(db_session, sample_turma, disc, admin_user,
                      "AULA 11 EDUCAÇÃO AMBIENTAL.mp4")
        resp = _call(db_session, "AULA 11 EDUCACAO AMBIENTAL.mp4")
        assert resp.updated == 1

    def test_repetido_mesmo_nome_409(
        self, db_session, sample_turma, sample_professor_disciplina, admin_user
    ):
        disc = sample_professor_disciplina["disciplina"]
        _criar_report(db_session, sample_turma, disc, admin_user,
                      "AULA 12 HISTORIA.mp4", vimeo_link="https://vimeo.com/999")
        with pytest.raises(HTTPException) as exc:
            _call(db_session, "AULA 12 HISTORIA.mp4")
        assert exc.value.status_code == 409

    def test_nome_inexistente_404(self, db_session):
        with pytest.raises(HTTPException) as exc:
            _call(db_session, "NAO EXISTE 999.mp4")
        assert exc.value.status_code == 404

    def test_nome_vazio_422(self, db_session):
        with pytest.raises(HTTPException) as exc:
            _call(db_session, "   ")
        assert exc.value.status_code == 422

    def test_drive_url_nao_sobrescreve_video_link(
        self, db_session, sample_turma, sample_professor_disciplina, admin_user
    ):
        disc = sample_professor_disciplina["disciplina"]
        r = _criar_report(db_session, sample_turma, disc, admin_user,
                          "AULA 13 FISICA.mp4",
                          video_link="https://drive.google.com/file/d/ORIGINAL/view")
        resp = _call(db_session, "AULA 13 FISICA.mp4",
                     drive_url="https://drive.google.com/file/d/NOVO/view")
        assert resp.drive_updated == 0  # não sobrescreve video_link existente
        db_session.refresh(r)
        assert "ORIGINAL" in r.video_link


# ─── Endpoint GET /aulas-por-disciplina (planilhas técnicas) ──────────────────

def _criar_report_disc(db_session, turma, disc, user, nome, vimeo=None, drive=None, pdf=None):
    from app.models.class_report import ClassReport
    r = ClassReport(
        created_by=user.id, status="FINALIZADO", data_aula=date(2026, 6, 1),
        turno="Manhã", estudio="Estúdio 01", turma_id=turma.id, disciplina_id=disc.id,
        horario_aula="07:30 - 08:30", regular="Sim", tipo_aula="Transmissão ao vivo",
        canal_utilizado="1", conteudo_ministrado="Conteúdo", nome_ficheiro_gerado=nome,
        vimeo_link=vimeo, video_link=drive, slide_link=pdf,
    )
    db_session.add(r); db_session.commit(); db_session.refresh(r)
    return r


def _call_disc(db_session, disciplina, modalidade=None):
    from app.api.rotas_externas import aulas_por_disciplina
    return aulas_por_disciplina(
        _FakeRequest(), disciplina, modalidade, db_session, "test-external-key"
    )


class TestAulasPorDisciplina:
    def test_casa_e_retorna_linhas(
        self, db_session, sample_turma, sample_professor_disciplina, admin_user
    ):
        disc = sample_professor_disciplina["disciplina"]  # "MATEMÁTICA"
        _criar_report_disc(db_session, sample_turma, disc, admin_user,
                           "EM 1 TI MATEMATICA 01 06 26 FUNCOES.mp4",
                           vimeo="https://vimeo.com/1", drive="https://drive/d/1/view",
                           pdf="https://drive/d/slide1/view")
        # consulta com nome sem acento → deve casar "MATEMÁTICA"
        resp = _call_disc(db_session, "MATEMATICA")
        assert resp.disciplina_casada == "MATEMÁTICA"
        assert resp.total == 1
        linha = resp.linhas[0]
        assert linha.nome_arquivo == "EM 1 TI MATEMATICA 01 06 26 FUNCOES.mp4"
        assert linha.vimeo_url == "https://vimeo.com/1"
        assert linha.drive_url == "https://drive/d/1/view"
        assert linha.pdf_url == "https://drive/d/slide1/view"

    def test_links_vazios_viram_string_vazia(
        self, db_session, sample_turma, sample_professor_disciplina, admin_user
    ):
        disc = sample_professor_disciplina["disciplina"]
        _criar_report_disc(db_session, sample_turma, disc, admin_user,
                           "EM 1 TI MATEMATICA 02 06 26 SEM LINKS.mp4")
        resp = _call_disc(db_session, "Matemática")
        assert resp.total == 1
        assert resp.linhas[0].vimeo_url == ""
        assert resp.linhas[0].pdf_url == ""

    def test_disciplina_inexistente(self, db_session):
        resp = _call_disc(db_session, "DISCIPLINA QUE NAO EXISTE XYZ")
        assert resp.disciplina_casada is None
        assert resp.total == 0
        assert resp.linhas == []

    def test_casa_por_tokens_ignora_conectivos(
        self, db_session, sample_turma, admin_user
    ):
        from app.models.auxiliares import Disciplina
        disc = Disciplina(nome="MICROBIOLOGIA E CONSERVAÇÃO DE ALIMENTOS",
                          nomenclatura_padrao="MICRO")
        db_session.add(disc); db_session.commit(); db_session.refresh(disc)
        _criar_report_disc(db_session, sample_turma, disc, admin_user,
                           "EM 1 TI MICROBIOLOGIA 01 06 26 X.mp4", drive="https://d/1/view")
        # aba da planilha diz "dos Alimentos"; banco diz "DE ALIMENTOS" → casa por tokens
        resp = _call_disc(db_session, "Microbiologia e Conservação dos Alimentos")
        assert resp.disciplina_casada == "MICROBIOLOGIA E CONSERVAÇÃO DE ALIMENTOS"
        assert resp.total == 1

    def test_casa_por_subconjunto_prefixo_curso(
        self, db_session, sample_turma, admin_user
    ):
        from app.models.auxiliares import Disciplina
        disc = Disciplina(nome="AGROPECUÁRIA OLERICULTURA E PLANTAS MEDICINAIS",
                          nomenclatura_padrao="OLE")
        db_session.add(disc); db_session.commit(); db_session.refresh(disc)
        _criar_report_disc(db_session, sample_turma, disc, admin_user,
                           "AULA 38 OLERICULTURA X.mp4", drive="https://d/1/view")
        # aba (sem o prefixo do curso + plural) casa por subconjunto
        resp = _call_disc(db_session, "Olericultura e Plantas medicinais")
        assert resp.disciplina_casada == "AGROPECUÁRIA OLERICULTURA E PLANTAS MEDICINAIS"
        assert resp.total == 1

    def test_casa_plural_singular(self, db_session, sample_turma, admin_user):
        from app.models.auxiliares import Disciplina
        disc = Disciplina(nome="GAME DESIGN E NARRATIVA INTERATIVA", nomenclatura_padrao="GD")
        db_session.add(disc); db_session.commit(); db_session.refresh(disc)
        _criar_report_disc(db_session, sample_turma, disc, admin_user, "AULA 1 GAME.mp4")
        resp = _call_disc(db_session, "Game Design e Narrativas Interativas")
        assert resp.disciplina_casada == "GAME DESIGN E NARRATIVA INTERATIVA"
        assert resp.total == 1

    def test_filtra_por_modalidade_tecnico(
        self, db_session, sample_turma, admin_user
    ):
        from app.models.auxiliares import Disciplina
        from app.models.turma import Turma

        disc = Disciplina(nome="ECONOMIA E MERCADOS", nomenclatura_padrao="ECO")
        turma_tecnico = Turma(
            nome="TÉCNICO EM ADMINISTRAÇÃO - MANHÃ",
            modalidade="TECNICO",
            serie_modulo="1º Módulo",
            turno="MANHÃ",
            nomenclatura_padrao="TEC ADM",
        )
        db_session.add(disc)
        db_session.add(turma_tecnico)
        db_session.commit()
        db_session.refresh(disc)
        db_session.refresh(turma_tecnico)

        _criar_report_disc(
            db_session, sample_turma, disc, admin_user,
            "EM 1 TIM ECONOMIA E MERCADOS 01 06 26 INTRO.mp4",
            drive="https://drive/d/regular/view",
        )
        _criar_report_disc(
            db_session, turma_tecnico, disc, admin_user,
            "AULA 01 ECONOMIA E MERCADOS INTRODUCAO.mp4",
            drive="https://drive/d/tecnico/view",
        )

        resp_todas = _call_disc(db_session, "ECONOMIA E MERCADOS")
        assert resp_todas.total == 2

        resp_tecnico = _call_disc(db_session, "ECONOMIA E MERCADOS", modalidade="TECNICO")
        assert resp_tecnico.disciplina_casada == "ECONOMIA E MERCADOS"
        assert resp_tecnico.total == 1
        assert resp_tecnico.linhas[0].nome_arquivo == "AULA 01 ECONOMIA E MERCADOS INTRODUCAO.mp4"
        assert resp_tecnico.linhas[0].drive_url == "https://drive/d/tecnico/view"

        resp_regular = _call_disc(db_session, "ECONOMIA E MERCADOS", modalidade="REGULAR")
        assert resp_regular.total == 1
        assert "EM 1 TIM" in resp_regular.linhas[0].nome_arquivo
