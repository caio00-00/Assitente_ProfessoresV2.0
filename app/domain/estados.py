"""
Canal Educação v4 — Máquina de estados dos relatórios (assistente e diretor).

Antes do v4 cada rota conferia o status do seu jeito: finalizar aceitava um
relatório já VALIDADO (ele voltava para a fila mantendo o validador antigo) e
editar não olhava o status. Aqui ficam as transições permitidas, iguais para os
dois relatórios.

    RASCUNHO ──finalizar──▶ AGUARDANDO_VALIDACAO ──validar──▶ VALIDADO
        ▲                        │      ▲                          │
        └──────devolver──────────┘      └────reabrir (edição)──────┤
        ▲                                                          │
        └─────────────────────devolver─────────────────────────────┘
    qualquer status (menos CANCELADO) ──cancelar──▶ CANCELADO (final)

FINALIZADO é o status antigo (antes da fila de validação): é tratado como
AGUARDANDO_VALIDACAO em todas as regras.
"""

from fastapi import HTTPException

RASCUNHO = "RASCUNHO"
AGUARDANDO = "AGUARDANDO_VALIDACAO"
VALIDADO = "VALIDADO"
CANCELADO = "CANCELADO"
FINALIZADO_LEGADO = "FINALIZADO"

STATUS_FINALIZADOS = frozenset({AGUARDANDO, VALIDADO, FINALIZADO_LEGADO})

TRANSICOES = {
    # Finalizar de novo um relatório que já está na fila refaz as conferências
    # (o botão "Salvar e finalizar" das telas faz isso). VALIDADO não volta.
    "finalizar": {RASCUNHO: AGUARDANDO, AGUARDANDO: AGUARDANDO, FINALIZADO_LEGADO: AGUARDANDO},
    "validar": {AGUARDANDO: VALIDADO, FINALIZADO_LEGADO: VALIDADO},
    "devolver": {AGUARDANDO: RASCUNHO, FINALIZADO_LEGADO: RASCUNHO, VALIDADO: RASCUNHO},
    # Reabrir acontece quando a coordenação (ou diretor-chefe) edita um VALIDADO:
    # o relatório volta para a fila e precisa ser validado de novo.
    "reabrir": {VALIDADO: AGUARDANDO},
    "cancelar": {RASCUNHO: CANCELADO, AGUARDANDO: CANCELADO, FINALIZADO_LEGADO: CANCELADO, VALIDADO: CANCELADO},
}

MENSAGENS = {
    "finalizar": {
        VALIDADO: "Este relatório já foi validado. Para alterar, peça à coordenação para devolvê-lo.",
        CANCELADO: "Relatório com status 'CANCELADO' não pode ser finalizado. Crie um novo.",
    },
    "validar": {
        RASCUNHO: "Só é possível validar relatórios com status 'Aguardando Validação'.",
        VALIDADO: "Este relatório já está validado.",
        CANCELADO: "Não é possível validar um relatório cancelado.",
    },
    "devolver": {
        RASCUNHO: "Só é possível solicitar correção de relatórios 'Aguardando Validação' ou já 'Validados'.",
        CANCELADO: "Não é possível devolver um relatório cancelado.",
    },
    "cancelar": {CANCELADO: "Relatório já está cancelado."},
}


def destino(acao: str, status_atual: str) -> str:
    """Devolve o novo status ou levanta 400 explicando por que a transição não vale."""
    status_atual = status_atual or RASCUNHO
    novo = TRANSICOES[acao].get(status_atual)
    if novo is None:
        msg = MENSAGENS.get(acao, {}).get(
            status_atual, f"Ação '{acao}' não é permitida para relatórios com status {status_atual}."
        )
        raise HTTPException(status_code=400, detail=msg)
    return novo


def pode_transicionar(acao: str, status_atual: str) -> bool:
    return (status_atual or RASCUNHO) in TRANSICOES[acao]


def esta_finalizado(status_atual: str) -> bool:
    return status_atual in STATUS_FINALIZADOS
