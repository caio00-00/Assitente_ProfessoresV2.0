"""
Canal Educação v4 — Política única de permissões.

Antes do v4 cada rota decidia sozinha quem podia o quê (listas PAPEIS_* em vários
arquivos, checagens de dono só em algumas rotas). Resultado: auditor escrevia,
assistente editava relatório de outro, qualquer usuário alterava turmas.

Aqui fica a tabela papel × ação, num lugar só. As rotas chamam `exigir(...)`.
A tabela é coberta por testes (tests/test_v4_politicas.py): mudar uma permissão
é mudar uma linha aqui e o teste correspondente.
"""

from typing import Optional

from fastapi import HTTPException, status

# ─── Papéis ───────────────────────────────────────────────────────────
ADMIN = "admin"
GESTOR = "gestor"
COORDENADOR = "coordenador"
COORDENADORA = "coordenadora"  # grafia antiga ainda presente em alguns usuários
AUDITOR = "auditor"
ASSISTENTE = "assistente"
DIRETOR_IMAGEM = "diretor_imagem"
DIRETOR_CHEFE = "diretor_chefe"

PAPEIS_VALIDOS = frozenset(
    {ADMIN, GESTOR, COORDENADOR, AUDITOR, ASSISTENTE, DIRETOR_IMAGEM, DIRETOR_CHEFE}
)
COORDENACAO = frozenset({ADMIN, GESTOR, COORDENADOR, COORDENADORA})
DIRETORES = frozenset({DIRETOR_IMAGEM, DIRETOR_CHEFE})


def normalizar_papel(papel: Optional[str]) -> str:
    """'coordenadora' é tratada como 'coordenador' (mesmo papel, grafia antiga)."""
    p = (papel or "").strip().lower()
    return COORDENADOR if p == COORDENADORA else p


# ─── Tabela de permissões ─────────────────────────────────────────────
# "proprio" = só quando o usuário é o autor do registro.
_TODOS_MENOS_DIRETORES = {ADMIN, GESTOR, COORDENADOR, AUDITOR, ASSISTENTE}

PERMISSOES = {
    # Relatório de aula (assistente)
    "relatorio_aula.ver": _TODOS_MENOS_DIRETORES,
    "relatorio_aula.criar": {ADMIN, GESTOR, COORDENADOR, ASSISTENTE},
    "relatorio_aula.editar": {ADMIN, GESTOR, COORDENADOR, ASSISTENTE},  # assistente: só o próprio
    "relatorio_aula.finalizar": {ADMIN, GESTOR, COORDENADOR, ASSISTENTE},  # assistente: só o próprio
    "relatorio_aula.cancelar": {ADMIN, GESTOR, COORDENADOR, ASSISTENTE},  # assistente: só o próprio
    "relatorio_aula.excluir": {ADMIN, ASSISTENTE},  # assistente: só o próprio rascunho
    "relatorio_aula.validar": {ADMIN, GESTOR, COORDENADOR},
    "relatorio_aula.devolver": {ADMIN, GESTOR, COORDENADOR},
    "relatorio_aula.editar_validado": {ADMIN, GESTOR, COORDENADOR},
    "relatorio_aula.reverificar_drive": {ADMIN, GESTOR, COORDENADOR, ASSISTENTE},
    # Histórico e linha do tempo da aula
    "historico.ver": {ADMIN, GESTOR, COORDENADOR, AUDITOR, ASSISTENTE, DIRETOR_CHEFE, DIRETOR_IMAGEM},
    "aula.linha_do_tempo": {ADMIN, GESTOR, COORDENADOR, AUDITOR, DIRETOR_CHEFE},
    # Cadastros
    "turma.ver": _TODOS_MENOS_DIRETORES | DIRETORES,
    "turma.escrever": {ADMIN, GESTOR},
    "grade.editar_slots": {ADMIN, GESTOR, COORDENADOR},
    # Faturamento
    "faturamento.exportar": {ADMIN, GESTOR, COORDENADOR, DIRETOR_CHEFE},
}

# Ações em que o assistente só pode agir sobre o que ele mesmo criou.
SO_PROPRIO_PARA_ASSISTENTE = {
    "relatorio_aula.editar",
    "relatorio_aula.finalizar",
    "relatorio_aula.cancelar",
    "relatorio_aula.excluir",
    "relatorio_aula.reverificar_drive",
}


def pode(usuario, acao: str, autor_id=None) -> bool:
    papel = normalizar_papel(getattr(usuario, "role", None))
    permitidos = PERMISSOES.get(acao)
    if permitidos is None:
        raise KeyError(f"Ação de permissão desconhecida: {acao}")
    if papel not in permitidos:
        return False
    if papel == ASSISTENTE and acao in SO_PROPRIO_PARA_ASSISTENTE and autor_id is not None:
        return str(autor_id) == str(getattr(usuario, "id", ""))
    return True


MENSAGENS = {
    "relatorio_aula.editar": "Você só pode editar relatórios criados por você.",
    # mesmas frases da v3 (as telas já mostram estas mensagens)
    "relatorio_aula.finalizar": "Assistentes só podem finalizar relatórios criados por eles mesmos.",
    "relatorio_aula.cancelar": "Assistentes só podem cancelar relatórios criados por eles mesmos.",
    "relatorio_aula.excluir": "Sem permissão para excluir este relatório. Apenas o criador ou Admin pode excluir.",
    "turma.escrever": "Só administração e gestão alteram turmas.",
}


def exigir(usuario, acao: str, autor_id=None) -> None:
    """Levanta 403 com mensagem clara quando o usuário não pode executar a ação."""
    if pode(usuario, acao, autor_id):
        return
    papel = normalizar_papel(getattr(usuario, "role", None))
    if papel == AUDITOR and acao.split(".")[-1] not in ("ver", "linha_do_tempo"):
        detalhe = "O perfil de auditoria é somente leitura."
    elif papel in DIRETORES and acao.startswith("relatorio_aula."):
        detalhe = "Este perfil não tem acesso a relatórios de aula."
    else:
        detalhe = MENSAGENS.get(acao, "Sem permissão para esta ação.")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detalhe)
