"""
Canal Educação v3.0 — Tests: Naming Engine
Unit tests for sanitization, naming format, P1/P2/P3 detection.
"""

from datetime import date

from app.services.naming_engine import (
    gerar_nome_padronizado,
    remover_acentos,
    sanitizar_conteudo,
    verificar_sufixo_geminada,
)


class TestRemoverAcentos:

    def test_remove_acentos_basicos(self):
        assert remover_acentos("Matemática") == "Matematica"

    def test_remove_acentos_multiplos(self):
        assert remover_acentos("Educação Física") == "Educacao Fisica"

    def test_sem_acentos_nao_muda(self):
        assert remover_acentos("BIOLOGIA") == "BIOLOGIA"

    def test_string_vazia(self):
        assert remover_acentos("") == ""

    def test_cedilha(self):
        assert remover_acentos("Ação") == "Acao"


class TestSanitizarConteudo:

    def test_remove_forbidden_windows_chars(self):
        result = sanitizar_conteudo('Teste: <script>"alert"</script> | file/path\\name')
        assert ":" not in result
        assert "<" not in result
        assert ">" not in result
        assert '"' not in result
        assert "|" not in result
        assert "/" not in result
        assert "\\" not in result

    def test_preserves_accents_and_case(self):
        result = sanitizar_conteudo("Funções do Primeiro Grau")
        assert result == "Funções do Primeiro Grau"

    def test_remove_espacos_extras(self):
        result = sanitizar_conteudo("  teste   com   espacos  ")
        assert "  " not in result
        assert result == "teste com espacos"


class TestGerarNomePadronizado:

    def test_formato_basico(self):
        nome = gerar_nome_padronizado(
            nomenclatura_turma="REGULAR 1ª SÉRIE MANHÃ",
            disciplina="Matemática",
            data_aula=date(2026, 3, 15),
            conteudo="Funções do primeiro grau",
        )
        assert "REGULAR" not in nome
        assert "1ª SÉRIE MANHÃ" in nome
        assert "MATEMÁTICA" in nome
        assert "FUNÇÕES DO PRIMEIRO GRAU" in nome
        assert nome.endswith(".mp4")

    def test_eja_sem_turno(self):
        nome = gerar_nome_padronizado(
            nomenclatura_turma="EJA ETAPA V",
            disciplina="Português",
            data_aula=date(2026, 5, 10),
            conteudo="Análise Sintática",
        )
        assert "EJA ETAPA V" in nome
        assert "PORTUGUÊS" in nome
        assert "ANÁLISE SINTÁTICA" in nome
        assert nome.endswith(".mp4")

    def test_ejatec(self):
        nome = gerar_nome_padronizado(
            nomenclatura_turma="EJATEC TEC ADM MOD1",
            disciplina="Física",
            data_aula=date(2026, 6, 1),
            conteudo="Mecânica",
        )
        assert "EJATEC TEC ADM MOD1" in nome
        assert "FÍSICA" in nome
        assert "MECÂNICA" in nome
        assert nome.endswith(".mp4")

    def test_sem_acentos_no_resultado(self):
        nome = gerar_nome_padronizado(
            nomenclatura_turma="EM 2 TI",
            disciplina="Educação Física",
            data_aula=date(2026, 1, 20),
            conteudo="Práticas esportivas",
        )
        assert "ã" not in nome
        assert "ç" not in nome
        assert "á" not in nome
        assert nome.endswith(".mp4")

    def test_sem_hifens_underscores(self):
        nome = gerar_nome_padronizado(
            nomenclatura_turma="EM 3 MANHÃ",
            disciplina="Artes",
            data_aula=date(2026, 6, 1),
            conteudo="Técnicas de pintura a óleo",
        )
        assert "-" not in nome
        assert "_" not in nome
        assert nome.endswith(".mp4")

    def test_nomenclatura_noite(self):
        nome = gerar_nome_padronizado(
            nomenclatura_turma="EM 1 NOITE",
            disciplina="Biologia",
            data_aula=date(2026, 3, 9),
            conteudo="Célula animal",
        )
        assert "EM 1 NOITE" in nome
        assert "BIOLOGIA" in nome
        assert "CÉLULA ANIMAL" in nome
        assert nome.endswith(".mp4")

    def test_turno_nao_duplica(self):
        """Regressão: 'EM 3 TARDE' NÃO deve gerar 'EM 3 TARDE TARDE'."""
        nome = gerar_nome_padronizado(
            nomenclatura_turma="EM 3 TARDE",
            disciplina="Educação Física",
            data_aula=date(2026, 2, 25),
            conteudo="Jogos Populares Regionais",
        )
        # Deve ser: EM 3 TARDE EDUCAÇÃO FÍSICA 25 02 26 JOGOS POPULARES REGIONAIS.mp4
        assert nome.count("TARDE") == 1
        assert "EM 3 TARDE EDUCAÇÃO FÍSICA" in nome
        assert nome.endswith(".mp4")


class TestVerificarSufixoGeminada:

    def test_com_p1(self):
        assert verificar_sufixo_geminada("Conteúdo P1") is True

    def test_com_p2(self):
        assert verificar_sufixo_geminada("Conteúdo P2") is True

    def test_com_p3(self):
        assert verificar_sufixo_geminada("Conteúdo P3") is True

    def test_sem_sufixo(self):
        assert verificar_sufixo_geminada("Conteúdo normal") is False

    def test_p4_invalido(self):
        assert verificar_sufixo_geminada("Conteúdo P4") is False

    def test_p1_no_meio(self):
        # P1 deve estar no final
        assert verificar_sufixo_geminada("P1 Conteúdo") is False


