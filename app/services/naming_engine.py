"""
Canal Educação v3.0 — Naming Engine (Motor de Nomenclatura).
Gera o nome padronizado do ficheiro MP4 conforme especificação:

  REGULAR / UAPI:
    [NOMENCLATURA_TURMA] [DISCIPLINA] [DATA_DD_MM_YY] [CONTEUDO].mp4

  TECNICO (obrigatório e inviolável):
    AULA [NN] [DISCIPLINA] [CONTEUDO].mp4

Preserva acentos para bater com os arquivos do Google Drive.
"""

import re
import unicodedata
from datetime import date
from typing import Optional


def remover_acentos(texto: str) -> str:
    """Remove toda acentuação do texto (NFKD decomposition)."""
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn")


def sanitizar_conteudo(texto: str) -> str:
    """
    Sanitização restrita a regras do Windows:
    - Remove apenas: \\ / : * ? " < > |
    - Preserva acentos originais e case.
    - Normaliza espaços.
    """
    # 1. Remove caracteres proibidos do Windows
    texto = re.sub(r'[\\/:*?"<>|]', '', texto)

    # 2. Normaliza espaços múltiplos
    texto = re.sub(r"\s+", " ", texto).strip()

    return texto


def gerar_nome_tecnico(
    disciplina: str,
    conteudo: str,
) -> str:
    """
    Regra OBRIGATÓRIA para turmas TECNICO:
    AULA [NN] [DISCIPLINA] [CONTEUDO].mp4
    
    Espera-se que o front-end já envie o `conteudo` iniciando com "AULA NN ".
    """
    # Parse com regex conforme requisito da Correção 4
    match = re.match(r"^AULA\s+(\d{2,4})\s+(.+)$", conteudo.strip(), flags=re.IGNORECASE)
    
    if not match:
        raise ValueError(
            f"conteudo_ministrado fora do padrão TECNICO: '{conteudo}'. "
            f"Requer revisão manual."
        )

    num_aula = match.group(1)
    assunto = match.group(2)

    disc_limpo = disciplina.strip().upper()
    cont_limpo = sanitizar_conteudo(assunto).upper()

    partes = [f"AULA {num_aula}", disc_limpo, cont_limpo]
    nome_base = " ".join(p for p in partes if p)

    # Limpeza final de hifens/underscores
    nome_base = re.sub(r'[\-_]', ' ', nome_base)
    nome_base = re.sub(r'\s+', ' ', nome_base).strip()

    nome_final = re.sub(r'(?i)\.mp4$', '', nome_base).strip()
    return f"{nome_final}.mp4"


def gerar_nome_padronizado(
    nomenclatura_turma: str,
    disciplina: str,
    data_aula: date,
    conteudo: str,
    modalidade: Optional[str] = None,
) -> str:
    """
    Dispatcher central. Escolhe a regra de nomenclatura baseando-se na modalidade.
    - modalidade == "TECNICO" → gerar_nome_tecnico()
    - Qualquer outro valor (REGULAR, UAPI, None) → padrão original.
    """
    modal_upper = (modalidade or "REGULAR").strip().upper()

    if modal_upper == "TECNICO":
        return gerar_nome_tecnico(
            disciplina=disciplina,
            conteudo=conteudo,
        )

    # ── Padrão REGULAR / UAPI (comportamento original intacto) ──────────
    # 1. Limpa nomenclatura — preserva acentos, remove "REGULAR"
    turma_limpo = nomenclatura_turma.strip()
    turma_limpo = re.sub(r'^REGULAR\s*', '', turma_limpo, flags=re.IGNORECASE)
    turma_limpo = turma_limpo.upper()

    # 2. Disciplina limpa — preserva acentos
    disc_limpo = disciplina.strip().upper()

    # 3. Data formatada (DD MM YY)
    data_str = data_aula.strftime("%d %m %y")

    # 4. Conteúdo higienizado — convertido para maiúsculo
    cont_limpo = sanitizar_conteudo(conteudo).upper()

    # 5. Monta o nome base
    partes = [turma_limpo, disc_limpo, data_str, cont_limpo]
    nome_base = " ".join(p for p in partes if p)

    # Limpeza final de hifens/underscores
    nome_base = re.sub(r'[\-_]', ' ', nome_base)
    nome_base = re.sub(r'\s+', ' ', nome_base).strip()

    # 6. Extensão .mp4 — sem truncamento para não cortar o conteúdo
    nome_final = re.sub(r'(?i)\.mp4$', '', nome_base).strip()

    return f"{nome_final}.mp4"


def verificar_sufixo_geminada(conteudo: str) -> bool:
    """Verifica se o conteúdo já possui sufixo P1, P2, P3 ou NP."""
    # Permite sufixo colado ou com espaço/hífen/underscore
    return bool(re.search(r"(?:^|\s|_|-|)(P[1-3]|NP)$", conteudo.strip().upper()))