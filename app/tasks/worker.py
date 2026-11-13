import time
import os
from datetime import datetime, timezone, timedelta
from celery import Celery
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.config import get_settings
from app.models.class_report import ClassReport
from app.services.sync_drive import buscar_video_no_drive, buscar_slide_no_drive
from app.services.compliance import compliance_completo, corrigir_verdes_pendentes

settings = get_settings()

def agendar_verificacao_inicial(report_id, nome_padronizado: str):
    """
    Agenda a verificação de compliance com o ATRASO INICIAL configurado
    (fluxo: finaliza → Pendente → aguarda ~2,5h → verifica → libera Verde).
    Usado na finalização e na edição que muda a nomenclatura — o arquivo só
    costuma chegar ao Drive depois desse período, então não adianta checar já.
    """
    from app.services.fila_compliance import renovar_fila, ttl_padrao_fila

    # v4: marca o relatório como "na fila" para a varredura de 30 min não agendar
    # outra verificação igual enquanto esta espera
    renovar_fila(report_id, ttl_padrao_fila())
    verificar_compliance_drive.apply_async(
        args=[str(report_id), nome_padronizado],
        countdown=settings.COMPLIANCE_INITIAL_DELAY_SECONDS,
    )


def _enfileirar_se_livre(report_id, nome: str) -> bool:
    """v4: usado pelas varreduras — só agenda se não houver verificação esperando."""
    from app.services.fila_compliance import marcar_na_fila, ttl_padrao_fila

    if not marcar_na_fila(report_id, ttl_padrao_fila(0)):
        return False
    verificar_compliance_drive.delay(str(report_id), nome)
    return True


# Resultados de verificar_uma_vez
VERDE, FALTOU, ADIADO, IGNORADO = "verde", "faltou", "adiado", "ignorado"


def verificar_uma_vez(report_id, nome_padronizado: str, exigir_diretor: bool = True) -> str:
    """
    Uma tentativa de busca do vídeo e do PDF no Drive, gravando os links.

    v4.1: o miolo da antiga tarefa Celery, separado para rodar também sem
    worker (modo "direto", usado na Vercel). Quem chama decide o que fazer
    quando falta arquivo: o Celery agenda nova tentativa; o modo direto deixa
    para a próxima varredura.

    Retorna VERDE (achou os dois), FALTOU (falta algum), ADIADO (bloqueado
    pelas regras do diretor de imagem) ou IGNORADO (relatório sumiu, foi
    cancelado ou mudou de nome).
    Reunião (out/2026): só busca depois que o diretor de imagem finalizou o
    relatório dele e com o vídeo NÃO marcado como corrompido.
    """
    import uuid as _uuid

    from app.services.fila_compliance import tirar_da_fila

    print(f"[WORKER] 🔍 Verificando compliance para relatório: {nome_padronizado} (ID: {report_id})")
    db = SessionLocal()
    try:
        try:
            rid = _uuid.UUID(str(report_id))
        except ValueError:
            rid = report_id
        report = db.query(ClassReport).filter(ClassReport.id == rid).first()

        if not report:
            print(f"[WORKER] ❌ Erro: Relatório {report_id} não encontrado.")
            tirar_da_fila(report_id)
            return IGNORADO

        # Tarefa agendada antes de uma edição que mudou o nome do arquivo.
        # A edição já agendou outra com o nome novo; esta não pode gravar link do antigo.
        if report.nome_ficheiro_gerado and nome_padronizado and report.nome_ficheiro_gerado != nome_padronizado:
            print(f"[WORKER] ⏭️ Nome mudou ({nome_padronizado} → {report.nome_ficheiro_gerado}); tarefa antiga encerrada.")
            return IGNORADO
        if report.is_deleted or report.status == "CANCELADO":
            tirar_da_fila(report_id)
            return IGNORADO

        report.compliance_verificado_em = datetime.now(timezone.utc)

        from app.services.busca_links import bloqueio_busca_link
        motivo = bloqueio_busca_link(db, report, exigir_diretor=exigir_diretor)
        if motivo:
            # Não busca agora: a busca volta quando o diretor finalizar / desmarcar o corrompido
            print(f"[WORKER] ⏸️ Busca adiada para {nome_padronizado}: {motivo}")
            if report.status_compliance != "Verde":
                report.status_compliance = "Pendente"
            db.commit()
            tirar_da_fila(report_id)
            return ADIADO

        faltou_arquivo = False  # só para o log

        # --- PDF, independente do vídeo ---
        if not report.slide_link:
            print(f"[WORKER] 🔍 Buscando slide para: {nome_padronizado}")
            slide_drive = buscar_slide_no_drive(nome_padronizado)
            if slide_drive:
                report.slide_link = slide_drive.get('webViewLink')
                print(f"[WORKER] ✅ Slide encontrado: {slide_drive.get('name')} -> {report.slide_link}")
                db.commit()
            else:
                print(f"[WORKER] ⚠️ Slide NÃO encontrado no Drive para: {nome_padronizado}")
                faltou_arquivo = True

        # --- Vídeo ---
        if not report.video_link:
            print(f"[WORKER] 🔍 Buscando vídeo para: {nome_padronizado}")
            video_drive = buscar_video_no_drive(nome_padronizado)

            if not video_drive:
                print(f"[WORKER] ⚠️ Vídeo NÃO encontrado no Drive para: {nome_padronizado}")
                faltou_arquivo = True
            else:
                link_encontrado = video_drive.get('webViewLink')
                md5_hash = video_drive.get('md5Checksum', 'N/A')
                size_bytes = int(video_drive.get('size', 0))

                # Vídeo pequeno demais é possivelmente corrompido (COMPLIANCE_MIN_VIDEO_MB)
                minimo_mb = getattr(settings, "COMPLIANCE_MIN_VIDEO_MB", 100)
                if size_bytes < minimo_mb * 1024 * 1024:
                    print(f"[WORKER][SRE] Falha de Integridade: vídeo abaixo de {minimo_mb}MB para: "
                          f"{nome_padronizado} ({size_bytes / (1024*1024):.2f} MB)")
                    faltou_arquivo = True
                else:
                    report.video_link = link_encontrado
                    report.md5_checksum = md5_hash
                    print(f"[WORKER] ✅ Vídeo encontrado e validado: {video_drive.get('name')} -> {link_encontrado}")
                    db.commit()

        if compliance_completo(report):
            report.status_compliance = "Verde"
            print(f"[WORKER] ✅ Ambos os arquivos encontrados. Status: Verde para: {nome_padronizado}")
            db.commit()
            tirar_da_fila(report_id)
            return VERDE

        report.status_compliance = "Pendente"
        db.commit()
        return FALTOU
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def marcar_vermelho(report_id) -> None:
    """Esgotou as tentativas: fica Vermelho até alguém reverificar."""
    import uuid as _uuid

    db = SessionLocal()
    try:
        report = db.query(ClassReport).filter(ClassReport.id == _uuid.UUID(str(report_id))).first()
        if report and report.status_compliance != "Verde":
            report.status_compliance = "Vermelho"
            db.commit()
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="verificar_compliance_drive",
    max_retries=settings.COMPLIANCE_MAX_RETRIES,
    autoretry_for=(Exception,),
    default_retry_delay=settings.COMPLIANCE_RETRY_INTERVAL_SECONDS,
    retry_jitter=False,
)
def verificar_compliance_drive(self, report_id: str, nome_padronizado: str, exigir_diretor: bool = True):
    """Tarefa Celery: uma tentativa e, se faltar arquivo, agenda a próxima."""
    from app.services.fila_compliance import (
        iniciar_execucao, renovar_fila, terminar_execucao, tirar_da_fila,
    )

    # Uma verificação por relatório de cada vez
    if not iniciar_execucao(report_id):
        print(f"[WORKER] ⏭️ Outra verificação já está rodando para {report_id}; esta desiste.")
        return False
    try:
        resultado = verificar_uma_vez(report_id, nome_padronizado, exigir_diretor)
        if resultado != FALTOU:
            return resultado == VERDE
        # Re-tenta em intervalo FIXO (config) até achar o arquivo.
        try:
            renovar_fila(report_id, 2 * settings.COMPLIANCE_RETRY_INTERVAL_SECONDS)
            raise self.retry(countdown=settings.COMPLIANCE_RETRY_INTERVAL_SECONDS)
        except MaxRetriesExceededError:
            print(f"[WORKER] ❌ Limite máximo de tentativas esgotado para: {nome_padronizado}")
            marcar_vermelho(report_id)
            tirar_da_fila(report_id)
            return False
    finally:
        terminar_execucao(report_id)


@celery_app.task(name="heartbeat_sistema")
def heartbeat_sistema():
    print("[WORKER] Heartbeat: Sistema de automação operacional ativo.")
    return "OK"

@celery_app.task(name="sincronizacao_noturna_drive")
def sincronizacao_noturna_drive():
    """
    Varredura (Cron): Busca no banco todos os relatórios 'Pendentes'
    DENTRO DA JANELA de re-verificação automática (data_aula recente)
    e re-dispara a tarefa individual de verificação.
    Relatórios com data_aula fora da janela (settings.COMPLIANCE_MAX_AGE_DAYS)
    não são mais re-tentados automaticamente — só via botão "Reverificar".
    """
    print("[WORKER] 🌙 Iniciando Sincronização Noturna do Drive...")
    db = SessionLocal()
    try:
        corrigidos = corrigir_verdes_pendentes(db)
        if corrigidos:
            print(f"[WORKER] ✅ {corrigidos} relatório(s) com vídeo e PDF corrigido(s) para Verde.")
        max_age_days = getattr(settings, "COMPLIANCE_MAX_AGE_DAYS", 45)
        data_limite = datetime.now(timezone.utc).date() - timedelta(days=max_age_days)

        pendentes = (
            db.query(ClassReport)
            .filter(or_(ClassReport.video_link == None, ClassReport.slide_link == None))
            .filter(ClassReport.nome_ficheiro_gerado != None)
            .filter(ClassReport.is_deleted == False)
            .filter(ClassReport.status.in_(("FINALIZADO", "AGUARDANDO_VALIDACAO", "VALIDADO")))
            .filter(ClassReport.data_aula >= data_limite)
            .all()
        )

        agendados = sum(1 for p in pendentes if _enfileirar_se_livre(p.id, p.nome_ficheiro_gerado))

        print(f"[WORKER] ✅ Sincronização Noturna: {agendados} de {len(pendentes)} relatório(s) "
              f"dentro da janela de {max_age_days} dias re-agendado(s) (os demais já estavam na fila).")
        return agendados
    except Exception as e:
        print(f"[WORKER] ❌ Erro na Sincronização Noturna: {str(e)}")
        return 0
    finally:
        db.close()

@celery_app.task(name="reprocessar_vermelhos_drive")
def reprocessar_vermelhos_drive():
    """
    Safety-net (roda a cada 30 min). Re-checa relatórios NÃO-verdes (Pendente ou
    Vermelho, sem vídeo OU sem slide) que JÁ passaram da janela inicial de espera
    E cuja data_aula ainda está dentro da janela de re-verificação automática
    (settings.COMPLIANCE_MAX_AGE_DAYS, ~45 dias). Relatórios mais antigos que isso
    ficam parados no status atual (Vermelho/Pendente) e só voltam a ser
    verificados manualmente pelo botão "Reverificar".
    """
    db = SessionLocal()
    try:
        corrigidos = corrigir_verdes_pendentes(db)
        if corrigidos:
            print(f"[REPROCESSAR] ✅ {corrigidos} relatório(s) com vídeo e PDF corrigido(s) para Verde.")
        agora = datetime.now(timezone.utc)
        limite = agora - timedelta(seconds=settings.COMPLIANCE_INITIAL_DELAY_SECONDS)

        max_age_days = getattr(settings, "COMPLIANCE_MAX_AGE_DAYS", 45)
        data_limite_idade = agora.date() - timedelta(days=max_age_days)

        vermelhos = (
            db.query(ClassReport)
            .filter(
                ClassReport.status_compliance.in_(["Vermelho", "Pendente"]),
                ClassReport.nome_ficheiro_gerado.isnot(None),
                ClassReport.is_deleted == False,
                ClassReport.status.in_(("FINALIZADO", "AGUARDANDO_VALIDACAO", "VALIDADO")),
                ClassReport.created_at < limite,
                ClassReport.data_aula >= data_limite_idade,
                or_(
                    ClassReport.video_link.is_(None),
                    ClassReport.slide_link.is_(None)
                )
            )
            .all()
        )

        total = len(vermelhos)
        print(f"[REPROCESSAR] 🔄 Encontrados {total} relatório(s) não-verdes dentro da janela de {max_age_days} dias para re-checar.")

        for report in vermelhos:
            sem_video = report.video_link is None
            sem_pdf = report.slide_link is None
            motivo = []
            if sem_video: motivo.append("sem vídeo")
            if sem_pdf: motivo.append("sem PDF")

            print(f"[REPROCESSAR] ↩️ {report.nome_ficheiro_gerado} ({', '.join(motivo)})")

            if _enfileirar_se_livre(report.id, report.nome_ficheiro_gerado):
                report.status_compliance = "Pendente"
                db.commit()
            else:
                total -= 1

        print(f"[REPROCESSAR] ✅ {total} relatório(s) re-enfileirado(s) (os demais já estavam na fila).")

    except Exception as e:
        print(f"[REPROCESSAR] ❌ Erro: {e}")
    finally:
        db.close()