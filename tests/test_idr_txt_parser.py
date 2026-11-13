"""Tests for IDR txt parser."""

from app.services.idr_txt_parser import normalize_canal, parse_idr_txt


SAMPLE = """
SÉRIE: 2ª SÉRIE INTEGRAL
TURNO: TARDE
DATA: 05/08/2026
DIRETOR: GILBERTO ROCHA
HORÁRIO DE ENTRADA/SAÍDA: 13:00 / 18:00
ESTÚDIO: 02
LINK DO YOUTUBE: https://www.youtube.com/live/532noKWZ3mI?feature=share
CANAL IPTV: SEDUC-PI2
====================================================================================
AULA 05
DISCIPLINA: FÍSICA
PROFESSOR: CAIO BRENO
DETALHAMENTO DA AULA:
- FOI TRANSMISSÃO OU AULA GRAVADA?
         TRANSMISSÃO
- VÍDEO CORROMPIDO?
	NÃO.
- INTERRUPÇÕES ANTES OU DURANTE A AULA?
	NÃO
- HOUVE PROBLEMA DE ÁUDIO?
	NÃO.
- FORAM COLOCADAS AS VINHETAS CORRETAMENTE?
	SIM.
- FORAM COLOCADOS OS CRÉDITOS CORRETOS?
	SIM.
OBS: SEM OBSERVAÇÃO
====================================================================================
"""


def test_parse_standard_txt():
    report = parse_idr_txt(SAMPLE, "sample.txt")
    assert report.data_relatorio.isoformat() == "2026-08-05"
    assert report.turno == "Tarde"
    assert report.estudio == "ESTÚDIO 2"
    assert report.diretor == "GILBERTO ROCHA"
    assert len(report.lessons) == 1
    assert report.lessons[0].disciplina == "FÍSICA"
    assert report.lessons[0].transmissao_ou_gravada == "Transmissão"


EMPTY_CANAL_SAMPLE = """
SÉRIE: 2ª SÉRIE INTEGRAL
TURNO: TARDE
DATA: 05/08/2026
DIRETOR: GILBERTO ROCHA
ESTÚDIO: 01
CANAL IPTV:
====================================================================================
AULA 01
DISCIPLINA: FILOSOFIA/SOCIOLOGIA
PROFESSOR: PROFº MAC DOWELL
DETALHAMENTO DA AULA:
- FOI TRANSMISSÃO OU AULA GRAVADA?
         TRANSMISSÃO
- VÍDEO CORROMPIDO?
	NÃO.
"""


def test_canal_iptv_ignores_separator_line():
    report = parse_idr_txt(EMPTY_CANAL_SAMPLE, "empty_canal.txt")
    assert report.canal_iptv is None
    assert report.lessons[0].canal_utilizado is None


def test_normalize_canal_rejects_separator():
    assert normalize_canal("====================================================================================") is None
    assert normalize_canal("SEDUC-PI2") == "SEDUC-PI2"


PROFESSOR_NEXT_LINE = """
SÉRIE: CURSO TÉCNICO
TURNO: TARDE
DATA: 12/08/2026
DIRETOR: GILBERTO ROCHA
ESTÚDIO: 02
AULA 01
DISCIPLINA: BOAS PRÁTICAS
PROFESSOR:
DETALHAMENTO DA AULA:
- FOI TRANSMISSÃO OU AULA GRAVADA?
         TRANSMISSÃO
- VÍDEO CORROMPIDO?
	NÃO.
"""


def test_professor_skips_detalhamento_label():
    report = parse_idr_txt(PROFESSOR_NEXT_LINE, "prof.txt")
    assert report.lessons == []


def test_infer_turno_from_serie():
    from app.services.idr_txt_parser import infer_turno_from_text

    assert infer_turno_from_text("CURSOS TÉCNICOS | CANAL EDUCAÇÃO | TARDE |") == "Tarde"
    assert infer_turno_from_text("ESTUDIO 2 TARDE 12082026.txt") == "Tarde"
