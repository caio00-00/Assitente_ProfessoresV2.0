"""
Canal Educação v4 — Travas da fila de verificação no Drive.

Antes do v4 a varredura de 30 em 30 minutos reenfileirava todo relatório não
verde dos últimos 45 dias, mesmo os que já tinham uma verificação esperando ou
em andamento. Cada uma ainda podia ter 20 novas tentativas. O mesmo relatório
chegava a ter várias cadeias chamando a API do Drive ao mesmo tempo.

Duas chaves no Redis por relatório:
- compliance:fila:<id>      → existe uma verificação agendada/esperando;
                              a varredura não agenda outra.
- compliance:rodando:<id>   → uma verificação está rodando agora;
                              uma segunda que chegue junto desiste.

Sem Redis (testes, ambiente local sem worker) as travas liberam sempre: o
comportamento fica igual ao de antes, nunca bloqueia por engano.
"""

import logging
from typing import Optional

from app.core.config import get_settings

log = logging.getLogger(__name__)
_cliente = {"redis": None, "falhou": False}


def _redis():
    if _cliente["falhou"]:
        return None
    if get_settings().modo_tarefas == "direto":
        # v4.1: sem worker (Vercel) não há Redis; não tenta conectar a cada chamada
        return None
    if _cliente["redis"] is None:
        try:
            import redis

            _cliente["redis"] = redis.Redis.from_url(get_settings().REDIS_URL, socket_timeout=2)
            _cliente["redis"].ping()
        except Exception as e:  # noqa: BLE001
            log.warning("travas da fila sem Redis (%s): seguindo sem trava", e)
            _cliente["falhou"] = True
            _cliente["redis"] = None
    return _cliente["redis"]


def _chave(tipo: str, report_id) -> str:
    return f"compliance:{tipo}:{report_id}"


def marcar_na_fila(report_id, ttl_segundos: int) -> bool:
    """True se marcou agora (pode agendar); False se já havia uma verificação esperando."""
    r = _redis()
    if r is None:
        return True
    try:
        return bool(r.set(_chave("fila", report_id), "1", nx=True, ex=max(60, int(ttl_segundos))))
    except Exception:  # noqa: BLE001
        return True


def renovar_fila(report_id, ttl_segundos: int) -> None:
    r = _redis()
    if r is None:
        return
    try:
        r.set(_chave("fila", report_id), "1", ex=max(60, int(ttl_segundos)))
    except Exception:  # noqa: BLE001
        pass


def tirar_da_fila(report_id) -> None:
    r = _redis()
    if r is None:
        return
    try:
        r.delete(_chave("fila", report_id))
    except Exception:  # noqa: BLE001
        pass


def iniciar_execucao(report_id, ttl_segundos: int = 600) -> bool:
    """True se esta execução pode rodar; False se outra já está rodando para o relatório."""
    r = _redis()
    if r is None:
        return True
    try:
        return bool(r.set(_chave("rodando", report_id), "1", nx=True, ex=ttl_segundos))
    except Exception:  # noqa: BLE001
        return True


def terminar_execucao(report_id) -> None:
    r = _redis()
    if r is None:
        return
    try:
        r.delete(_chave("rodando", report_id))
    except Exception:  # noqa: BLE001
        pass


def ttl_padrao_fila(atraso_inicial: Optional[int] = None) -> int:
    cfg = get_settings()
    atraso = cfg.COMPLIANCE_INITIAL_DELAY_SECONDS if atraso_inicial is None else atraso_inicial
    return atraso + 2 * cfg.COMPLIANCE_RETRY_INTERVAL_SECONDS
