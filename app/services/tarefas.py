"""
Canal Educação v4.1 — Quem executa a busca no Drive.

O mesmo código roda de dois jeitos (Settings.modo_tarefas):

- "celery" (Docker / Dokploy): como sempre — a API põe a tarefa na fila do
  Redis e o worker executa, com atraso inicial de ~2,5 h e novas tentativas.
- "direto" (Vercel): não há worker nem Redis. Nada é agendado; a busca roda na
  própria API em três momentos:
    1. "Buscar no Drive" na tela de Relatórios de aula (varredura);
    2. "Reverificar" num relatório (só aquele, na hora);
    3. a rota /api/v1/sistema/varredura, chamada por um cron.
  A varredura respeita as mesmas regras do worker: espera o atraso inicial
  depois da finalização, só olha aulas dentro da janela de COMPLIANCE_MAX_AGE_DAYS,
  e marca Vermelho quando passa do tempo que as tentativas do worker levariam.

As rotas chamam só as funções daqui, então não precisam saber onde estão rodando.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.core.config import get_settings

log = logging.getLogger(__name__)

STATUS_COM_BUSCA = ("FINALIZADO", "AGUARDANDO_VALIDACAO", "VALIDADO")


def modo() -> str:
    return get_settings().modo_tarefas


def agendar_verificacao(report_id, nome: str) -> None:
    """Depois de finalizar (ou de mudar o nome do arquivo)."""
    if modo() == "celery":
        from app.tasks.worker import agendar_verificacao_inicial

        agendar_verificacao_inicial(report_id, nome)
    # direto: nada a fazer agora; o arquivo só chega ao Drive depois do atraso
    # inicial, e a próxima varredura pega o relatório (status já é Pendente).


def verificar_agora(report_id, nome: str, exigir_diretor: bool = True) -> dict:
    """Uma verificação imediata (botão Reverificar, diretor finalizou)."""
    from app.tasks.worker import verificar_uma_vez

    if modo() == "celery":
        from app.tasks.worker import verificar_compliance_drive

        try:
            verificar_compliance_drive.delay(str(report_id), nome, exigir_diretor=exigir_diretor)
            return {"modo": "celery", "resultado": "na_fila"}
        except Exception as e:  # noqa: BLE001
            # HML 6047d52: com o Redis/Celery fora, verifica na hora em vez de dar erro 500
            log.warning("fila indisponível (%s); verificando direto no Drive", e)

    return {"modo": "direto", "resultado": verificar_uma_vez(report_id, nome, exigir_diretor)}


def varrer(db, tempo_max_segundos: int = None) -> dict:
    """
    Varredura geral. Celery: manda a sincronização para a fila. Direto: verifica
    aqui mesmo, começando pelos relatórios há mais tempo sem verificação, até
    acabar a lista ou o tempo (as funções da Vercel têm tempo máximo).
    """
    from app.services.compliance import corrigir_verdes_pendentes

    corrigidos = corrigir_verdes_pendentes(db)
    if modo() == "celery":
        from app.tasks.worker import sincronizacao_noturna_drive

        sincronizacao_noturna_drive.delay()
        return {"modo": "celery", "corrigidos_verde": corrigidos, "resultado": "na_fila"}

    from app.models.class_report import ClassReport
    from app.tasks.worker import FALTOU, VERDE, verificar_uma_vez

    s = get_settings()
    limite_tempo = time.monotonic() + (tempo_max_segundos or s.VARREDURA_TEMPO_MAX_SEGUNDOS)
    agora = datetime.now(timezone.utc)
    espera_inicial = agora - timedelta(seconds=s.COMPLIANCE_INITIAL_DELAY_SECONDS)
    # Tempo que o worker levaria para esgotar as tentativas → depois disso, Vermelho
    prazo_vermelho = timedelta(
        seconds=s.COMPLIANCE_INITIAL_DELAY_SECONDS + s.COMPLIANCE_MAX_RETRIES * s.COMPLIANCE_RETRY_INTERVAL_SECONDS
    )
    data_minima = agora.date() - timedelta(days=getattr(s, "COMPLIANCE_MAX_AGE_DAYS", 45))

    candidatos = (
        db.query(ClassReport.id, ClassReport.nome_ficheiro_gerado, ClassReport.created_at)
        .filter(
            ClassReport.nome_ficheiro_gerado.isnot(None),
            ClassReport.is_deleted == False,  # noqa: E712
            ClassReport.status.in_(STATUS_COM_BUSCA),
            ClassReport.status_compliance != "Verde",
            ClassReport.created_at < espera_inicial,
            ClassReport.data_aula >= data_minima,
            or_(ClassReport.video_link.is_(None), ClassReport.slide_link.is_(None)),
        )
        .order_by(ClassReport.compliance_verificado_em.asc().nullsfirst(), ClassReport.data_aula.desc())
        .all()
    )
    db.commit()  # solta a conexão antes das chamadas ao Drive

    contagem = {"verificados": 0, "verdes": 0, "faltando": 0, "vermelhos": 0, "outros": 0, "erros": 0}
    from app.tasks.worker import marcar_vermelho

    for rid, nome, criado in candidatos:
        if time.monotonic() > limite_tempo:
            break
        try:
            r = verificar_uma_vez(rid, nome)
        except Exception as e:  # noqa: BLE001 — um relatório com erro não para a varredura
            log.warning("varredura: erro em %s: %s", rid, e)
            contagem["erros"] += 1
            continue
        contagem["verificados"] += 1
        if r == VERDE:
            contagem["verdes"] += 1
        elif r == FALTOU:
            criado_utc = criado if (criado and criado.tzinfo) else (criado.replace(tzinfo=timezone.utc) if criado else agora)
            if agora - criado_utc > prazo_vermelho:
                marcar_vermelho(rid)
                contagem["vermelhos"] += 1
            else:
                contagem["faltando"] += 1
        else:
            contagem["outros"] += 1

    return {
        "modo": "direto",
        "corrigidos_verde": corrigidos,
        "na_lista": len(candidatos),
        "restantes": max(0, len(candidatos) - contagem["verificados"] - contagem["erros"]),
        **contagem,
    }
