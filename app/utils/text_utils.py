"""
Canal Educação v3.0 — Utilitários de Texto.
Sanitização de nomes de arquivo e parsing de habilidades BNCC.
"""

import re
import unicodedata
from typing import List


def is_placeholder_professor(nome: str | None) -> bool:
    """True quando o nome não é um professor real (N/A, vazio, traço, etc.)."""
    n = (nome or "").strip().lower()
    return not n or n in {"n/a", "na", "—", "-", "desconhecido"}


def normalizar_para_match(nome: str) -> str:
    """
    Normaliza o nome de um arquivo para casamento robusto entre sistemas
    (Assistente ↔ Vimeo Sync): remove extensão .mp4, acentos, caixa e tudo
    que não seja letra/número. Espelha sync_drive.normalize_for_search.
    """
    if not nome:
        return ""
    base = re.sub(r"(?i)\.mp4$", "", nome.strip())
    nfkd = unicodedata.normalize("NFKD", base)
    base = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", base.lower())


# ─── Sanitização de Nomes ─────────────────────────────────────────────

def higienizar_nome_arquivo(nome_original: str) -> str:
    """
    BA008: Motor de Sanitização.
    Remove caracteres inválidos para sistemas de arquivos e URLs.
    Regex base: [\/:*?"<>|
]    """
    # Define o padrão de caracteres proibidos
    padrao_proibido = r'[\\/:*?"<>|]'

    # Substitui os caracteres proibidos por uma string vazia
    nome_limpo = re.sub(padrao_proibido, '', nome_original)

    # Refinamento: Remove espaços duplos criados após a remoção
    nome_limpo = re.sub(r'\s+', ' ', nome_limpo)

    return nome_limpo.strip()


# ─── Parser de Habilidades BNCC ───────────────────────────────────────

HABILIDADE_REGEX = re.compile(r"\(([\w]+)\)\s*(.*)")


def parse_habilidade_string(texto_bruto: str) -> dict:
    """
    Converte uma linha no formato '(CODIGO) descrição' em um dicionário.

    Retorna:
        {"codigo": "EM13CHS206", "descricao": "Analisar a ocupação..."}

    Trata:
        - Texto vazio ou None → codigo N/A
        - Formato inválido    → codigo FORMATO_INVALIDO
        - JSON-encoded string → remove aspas externas
    """
    if not texto_bruto:
        return {
            "codigo": "N/A",
            "descricao": "Sem registro de habilidade.",
        }

    # Limpa aspas externas caso o valor venha de coluna JSON
    texto = texto_bruto.strip()
    if texto.startswith('"') and texto.endswith('"'):
        texto = texto[1:-1]

    match = HABILIDADE_REGEX.search(texto)
    if match:
        return {
            "codigo": match.group(1).strip(),
            "descricao": match.group(2).strip(),
        }

    return {
        "codigo": "FORMATO_INVALIDO",
        "descricao": texto.strip(),
    }


def parse_habilidades_list(texto_bruto: str | None) -> List[dict]:
    """
    Converte o campo bncc_habilidades (pode ter múltiplas linhas) em uma
    lista de dicionários {codigo, descricao}.

    Cada linha do texto bruto é tratada como uma habilidade independente.
    Linhas vazias são ignoradas.
    """
    if not texto_bruto:
        return []

    # Suporte a múltiplas habilidades por linha (separadas por \n)
    linhas = [l.strip() for l in str(texto_bruto).splitlines() if l.strip()]

    if not linhas:
        return []

    resultado = []
    for linha in linhas:
        parsed = parse_habilidade_string(linha)
        resultado.append(parsed)

    return resultado
