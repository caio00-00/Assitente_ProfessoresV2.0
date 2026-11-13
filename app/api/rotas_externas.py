"""
Canal Educação v3.0 — API Externa M2M (Estudologia).
Endpoints para consulta de habilidades pedagógicas BNCC.

Prefixo: /api/v1/external
Autenticação: Header X-API-Key (chave estática M2M)

Endpoints disponíveis:
    GET /habilidades/por-ficheiro   → por report_id
    GET /habilidades/por-turma      → por turma_id
    GET /habilidades/por-disciplina → por nome da disciplina
    GET /habilidades/por-periodo    → por ano + mes
"""

import re
import unicodedata
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_external_token
from app.models.audit_log import AuditLog
from app.models.auxiliares import Disciplina
from app.models.class_report import ClassReport
from app.models.turma import Turma
from app.schemas.external import (
    AulaLinha,
    AulasPorDisciplinaResponse,
    DisciplinaHabilidadesResponse,
    HabilidadeDetalhe,
    PeriodoHabilidadesResponse,
    PeriodoItemResponse,
    RelatorioHabilidadeResponse,
    TurmaHabilidadesAgregadas,
    VimeoLinkInput,
    VimeoLinkResponse,
)
from app.utils.text_utils import normalizar_para_match, parse_habilidades_list

router = APIRouter(
    prefix="/api/v1/external",
    tags=["API Externa M2M"],
)


# ─── Helpers ─────────────────────────────────────────────────────────


def _get_client_ip(request: Request) -> str:
    """Extrai IP real do cliente (suporta X-Forwarded-For de proxies)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _registrar_auditoria(db: Session, endpoint: str, ip: str) -> None:
    """
    Registra toda chamada externa na tabela audit_logs.
    actor_id = None pois não há usuário interno envolvido (acesso M2M).
    """
    log = AuditLog(
        actor_id=None,
        action="CONSULTA_EXTERNA",
        details=f"Acesso ao endpoint externo: {endpoint}",
        created_at=datetime.now(timezone.utc),
        ip_address=ip,
    )
    db.add(log)
    db.commit()


def _dicts_to_habilidades(dicts: list) -> list[HabilidadeDetalhe]:
    """Converte lista de dicts em lista de HabilidadeDetalhe."""
    return [HabilidadeDetalhe(codigo=d["codigo"], descricao=d["descricao"]) for d in dicts]


# Conectivos ignorados ao casar nomes de disciplina (de/da/dos/e/em/na...).
_DISC_STOPWORDS = {
    "de", "da", "do", "dos", "das", "e", "em", "na", "no", "nas", "nos",
    "a", "o", "as", "os", "com", "para", "por", "ao", "aos",
}


def _tokens_disciplina(nome: str) -> frozenset:
    """
    Conjunto de palavras significativas do nome: sem acento, sem conectivos
    (de/da/dos/e/em/na...) e com plural simples reduzido (remove "s" final) —
    assim "Narrativas" casa com "Narrativa", "Mentorias" com "Mentoria" etc.
    """
    if not nome:
        return frozenset()
    nfkd = unicodedata.normalize("NFKD", nome)
    base = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    tokens = set()
    for p in re.split(r"[^a-z0-9]+", base):
        if not p or p in _DISC_STOPWORDS:
            continue
        if len(p) > 3 and p.endswith("s"):
            p = p[:-1]  # plural simples
        tokens.add(p)
    return frozenset(tokens)


# ─── Endpoint 1: Habilidades por Ficheiro ────────────────────────────


@router.get(
    "/habilidades/por-ficheiro",
    response_model=RelatorioHabilidadeResponse,
    summary="Habilidades de um relatório específico",
)
def habilidades_por_ficheiro(
    request: Request,
    report_id: UUID = Query(..., description="UUID do relatório (class_report)"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_external_token),
):
    """
    Retorna todas as habilidades BNCC vinculadas a um relatório específico.
    """
    report = (
        db.query(ClassReport)
        .filter(ClassReport.id == report_id, ClassReport.is_deleted.is_(False))
        .first()
    )

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relatório '{report_id}' não encontrado.",
        )

    habilidades_raw = parse_habilidades_list(report.bncc_habilidades)
    habilidades = _dicts_to_habilidades(habilidades_raw)

    _registrar_auditoria(
        db,
        f"GET /habilidades/por-ficheiro?report_id={report_id}",
        _get_client_ip(request),
    )

    return RelatorioHabilidadeResponse(
        report_id=report.id,
        ficheiro_nome=report.nome_ficheiro_gerado,
        total_habilidades=len(habilidades),
        habilidades=habilidades,
    )


# ─── Endpoint 2: Habilidades por Turma ───────────────────────────────


@router.get(
    "/habilidades/por-turma",
    response_model=TurmaHabilidadesAgregadas,
    summary="Agregação de habilidades por turma",
)
def habilidades_por_turma(
    request: Request,
    turma_id: UUID = Query(..., description="UUID da turma"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_external_token),
):
    """
    Retorna agregação de habilidades BNCC para uma turma,
    com a contagem de ocorrências de cada código.
    """
    turma = db.query(Turma).filter(Turma.id == turma_id).first()

    if not turma:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turma '{turma_id}' não encontrada.",
        )

    reports = (
        db.query(ClassReport)
        .filter(
            ClassReport.turma_id == turma_id,
            ClassReport.is_deleted.is_(False),
            ClassReport.bncc_habilidades.isnot(None),
        )
        .all()
    )

    # Agrega contagem por código BNCC
    contagem: dict[str, int] = {}
    datas = []

    for report in reports:
        habilidades = parse_habilidades_list(report.bncc_habilidades)
        for h in habilidades:
            codigo = h["codigo"]
            if codigo not in ("N/A", "FORMATO_INVALIDO"):
                contagem[codigo] = contagem.get(codigo, 0) + 1
        if report.data_aula:
            datas.append(report.data_aula)

    # Período letivo: range de datas dos relatórios
    if datas:
        periodo_letivo = f"{min(datas).strftime('%d/%m/%Y')} a {max(datas).strftime('%d/%m/%Y')}"
    else:
        periodo_letivo = "Sem registros"

    _registrar_auditoria(
        db,
        f"GET /habilidades/por-turma?turma_id={turma_id}",
        _get_client_ip(request),
    )

    return TurmaHabilidadesAgregadas(
        turma_id=turma.id,
        turma_nome=turma.nomenclatura_padrao or turma.nome,
        periodo_letivo=periodo_letivo,
        habilidades_mapeadas=contagem,
    )


# ─── Endpoint 3: Habilidades por Disciplina ──────────────────────────


@router.get(
    "/habilidades/por-disciplina",
    response_model=DisciplinaHabilidadesResponse,
    summary="Códigos BNCC distintos por disciplina",
)
def habilidades_por_disciplina(
    request: Request,
    nome: str = Query(..., description="Nome (parcial) da disciplina", min_length=2),
    db: Session = Depends(get_db),
    _: str = Depends(verify_external_token),
):
    """
    Lista os códigos BNCC distintos associados a uma disciplina.
    A busca é case-insensitive e parcial (like %nome%).
    """
    disciplinas = (
        db.query(Disciplina)
        .filter(Disciplina.nome.ilike(f"%{nome}%"))
        .all()
    )

    if not disciplinas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhuma disciplina encontrada com nome '{nome}'.",
        )

    disciplina_ids = [d.id for d in disciplinas]
    disciplina_nomes = ", ".join(d.nome for d in disciplinas)

    reports = (
        db.query(ClassReport)
        .filter(
            ClassReport.disciplina_id.in_(disciplina_ids),
            ClassReport.is_deleted.is_(False),
            ClassReport.bncc_habilidades.isnot(None),
        )
        .all()
    )

    # Coleta códigos distintos (exclui inválidos)
    codigos_distintos: set[str] = set()
    for report in reports:
        habilidades = parse_habilidades_list(report.bncc_habilidades)
        for h in habilidades:
            codigo = h["codigo"]
            if codigo not in ("N/A", "FORMATO_INVALIDO"):
                codigos_distintos.add(codigo)

    codigos_lista = sorted(codigos_distintos)

    _registrar_auditoria(
        db,
        f"GET /habilidades/por-disciplina?nome={nome}",
        _get_client_ip(request),
    )

    return DisciplinaHabilidadesResponse(
        disciplina=disciplina_nomes,
        total_codigos_distintos=len(codigos_lista),
        habilidades=codigos_lista,
    )


# ─── Endpoint 4: Habilidades por Período ─────────────────────────────


@router.get(
    "/habilidades/por-periodo",
    response_model=PeriodoHabilidadesResponse,
    summary="Habilidades registradas em um período (ano/mês)",
)
def habilidades_por_periodo(
    request: Request,
    ano: int = Query(..., description="Ano (ex: 2026)", ge=2020, le=2100),
    mes: int = Query(..., description="Mês (1-12)", ge=1, le=12),
    db: Session = Depends(get_db),
    _: str = Depends(verify_external_token),
):
    """
    Retorna todas as habilidades BNCC registradas em um ano/mês específico.
    """
    reports = (
        db.query(ClassReport)
        .filter(
            ClassReport.is_deleted.is_(False),
            ClassReport.bncc_habilidades.isnot(None),
            extract("year", ClassReport.data_aula) == ano,
            extract("month", ClassReport.data_aula) == mes,
        )
        .order_by(ClassReport.data_aula)
        .all()
    )

    itens: list[PeriodoItemResponse] = []
    for report in reports:
        habilidades = parse_habilidades_list(report.bncc_habilidades)
        for h in habilidades:
            if h["codigo"] not in ("N/A", "FORMATO_INVALIDO"):
                itens.append(
                    PeriodoItemResponse(
                        report_id=report.id,
                        codigo=h["codigo"],
                        descricao=h["descricao"],
                        data_aula=report.data_aula,
                    )
                )

    periodo_label = f"{mes:02d}/{ano}"

    _registrar_auditoria(
        db,
        f"GET /habilidades/por-periodo?ano={ano}&mes={mes}",
        _get_client_ip(request),
    )

    return PeriodoHabilidadesResponse(
        periodo=periodo_label,
        total_habilidades_periodo=len(itens),
        data_extracao=datetime.now(timezone.utc),
        itens=itens,
    )


# ─── Endpoint 5: Integração Vimeo Sync (recebe o link do vídeo) ───────


@router.post(
    "/vimeo-link",
    response_model=VimeoLinkResponse,
    summary="Recebe o link do Vimeo de uma aula (push do Vimeo Sync)",
    responses={
        404: {"description": "Nenhum relatório casa com a nomenclatura"},
        409: {"description": "Relatório já possui vínculo (vimeo_link)"},
        422: {"description": "Payload inválido"},
    },
)
def receber_vimeo_link(
    request: Request,
    payload: VimeoLinkInput,
    db: Session = Depends(get_db),
    _: str = Depends(verify_external_token),
):
    """
    Casa o vídeo pelo NOME DO ARQUIVO com os relatórios de aula e grava o
    `vimeo_link` (e, se enviado e ainda vazio, `video_link` a partir de `drive_url`).
    O Vimeo Sync é quem fornece (push); o Assistente apenas recebe.

    Semântica de resposta (consumida pelo Sync):
      - 200: vínculo gravado (pelo menos um relatório recebeu o vimeo_link)
      - 404: nenhuma nomenclatura corresponde → Sync enfileira em vinculos_pendentes
      - 409: relatório(s) encontrado(s) mas já com vimeo_link → idempotente, não sobrescreve
      - 422: nome_ficheiro vazio/inválido
    """
    alvo = normalizar_para_match(payload.nome_ficheiro)
    if not alvo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="nome_ficheiro vazio ou inválido.",
        )

    # 1ª tentativa: casamento exato (case-insensitive) pelo nome gerado.
    nome_sem_ext = re.sub(r"(?i)\.mp4$", "", payload.nome_ficheiro.strip())
    candidatos = (
        db.query(ClassReport)
        .filter(
            ClassReport.is_deleted.is_(False),
            ClassReport.nome_ficheiro_gerado.isnot(None),
            func.lower(ClassReport.nome_ficheiro_gerado).in_(
                [payload.nome_ficheiro.strip().lower(), f"{nome_sem_ext.lower()}.mp4", nome_sem_ext.lower()]
            ),
        )
        .all()
    )

    # 2ª tentativa (fallback): casamento normalizado (acentos/caixa/separadores).
    # v4: usa a coluna indexada nome_normalizado (antes lia a tabela inteira em
    # memória a cada 404 do Sync).
    if not candidatos:
        candidatos = (
            db.query(ClassReport)
            .filter(
                ClassReport.is_deleted.is_(False),
                ClassReport.nome_normalizado == alvo,
            )
            .all()
        )

    # 404 — nenhuma nomenclatura corresponde (Sync é quem reenfileira).
    if not candidatos:
        _registrar_auditoria(
            db,
            f"POST /vimeo-link nome={payload.nome_ficheiro} matched=0 (404)",
            _get_client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhum relatório encontrado para a nomenclatura '{payload.nome_ficheiro}'.",
        )

    vimeo_atualizados: list = []
    drive_atualizados: list = []
    for report in candidatos:
        # Idempotência: só grava o vimeo_link se ainda estiver vazio (não sobrescreve).
        if not report.vimeo_link:
            report.vimeo_link = payload.vimeo_url
            vimeo_atualizados.append(report.id)
        # drive_url → video_link (mesmo arquivo no Drive); só preenche se vazio.
        # v4: respeita as mesmas travas da busca automática (diretor ainda não
        # finalizou, vídeo marcado como corrompido). Antes o link entrava direto.
        if payload.drive_url and not report.video_link:
            from app.services.busca_links import bloqueio_busca_link

            if bloqueio_busca_link(db, report) is None:
                report.video_link = payload.drive_url
                drive_atualizados.append(report.id)

    # drive_url gravou o vídeo do Drive: se o PDF já existe, fica Verde na hora
    from app.services.compliance import aplicar_verde_se_completo

    verdes = [r.id for r in candidatos if aplicar_verde_se_completo(r)]

    if vimeo_atualizados or drive_atualizados or verdes:
        db.commit()

    # 409 — encontrado mas todos já tinham vimeo_link (idempotente, não é erro).
    if not vimeo_atualizados:
        _registrar_auditoria(
            db,
            f"POST /vimeo-link nome={payload.nome_ficheiro} matched={len(candidatos)} "
            f"updated=0 drive={len(drive_atualizados)} (409)",
            _get_client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Relatório(s) já possuem vínculo de vídeo para '{payload.nome_ficheiro}'.",
        )

    _registrar_auditoria(
        db,
        f"POST /vimeo-link nome={payload.nome_ficheiro} matched={len(candidatos)} "
        f"updated={len(vimeo_atualizados)} drive={len(drive_atualizados)} (200)",
        _get_client_ip(request),
    )

    return VimeoLinkResponse(
        status="vinculado",
        matched=True,
        updated=len(vimeo_atualizados),
        drive_updated=len(drive_atualizados),
        report_ids=[r.id for r in candidatos],
        nome_ficheiro=payload.nome_ficheiro,
    )


# ─── Endpoint 6: Aulas por Disciplina (planilhas de cursos técnicos) ──


@router.get(
    "/aulas-por-disciplina",
    response_model=AulasPorDisciplinaResponse,
    summary="Aulas (arquivo + links) de uma disciplina, para preencher a planilha",
)
def aulas_por_disciplina(
    request: Request,
    disciplina: str = Query(..., min_length=2, description="Nome da disciplina (o nome da aba)"),
    modalidade: Optional[str] = Query(
        None,
        min_length=2,
        description="Filtra aulas pela modalidade da turma (ex.: TECNICO, REGULAR, UAPI).",
    ),
    db: Session = Depends(get_db),
    _: str = Depends(verify_external_token),
):
    """
    Recebe o nome de uma disciplina (o nome da aba da planilha), casa com a
    disciplina no banco (normalizado: acento/caixa/separadores) e devolve as
    aulas finalizadas dela com os 4 campos da planilha:
    nome do arquivo, link do Vimeo, link do Drive e link do PDF (slide).

    Quando ``modalidade`` é informada (ex.: TECNICO), retorna apenas relatórios
    de turmas com essa modalidade — útil quando a mesma disciplina existe em
    cursos regulares e técnicos.
    """
    modalidade_filtro = modalidade.strip().upper() if modalidade else None
    alvo = normalizar_para_match(disciplina)
    if not alvo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="disciplina vazia ou inválida.",
        )

    todas = db.query(Disciplina).all()

    # 1ª tentativa: casamento exato normalizado.
    casadas = [d for d in todas if normalizar_para_match(d.nome) == alvo]

    # 2ª tentativa: mesmo conjunto de palavras significativas (ignora conectivos
    # como de/dos/e/em/na e plural — cobre "...dos Alimentos" vs "...DE ALIMENTOS",
    # "Narrativas" vs "NARRATIVA" etc.).
    alvo_tokens = _tokens_disciplina(disciplina)
    if not casadas and alvo_tokens:
        casadas = [d for d in todas if _tokens_disciplina(d.nome) == alvo_tokens]

    # 3ª tentativa: a aba é um SUBCONJUNTO do nome no banco (ex.: o banco guarda o
    # prefixo do curso — "AGROPECUÁRIA OLERICULTURA E PLANTAS MEDICINAIS"). Pega o
    # nome com menos sobra de palavras. Mínimo de 2 tokens para evitar ruído.
    if not casadas and len(alvo_tokens) >= 2:
        supersets = [
            d for d in todas
            if (dt := _tokens_disciplina(d.nome)) and alvo_tokens <= dt
        ]
        if supersets:
            supersets.sort(key=lambda d: len(_tokens_disciplina(d.nome)))
            casadas = [supersets[0]]

    # 4ª tentativa (fallback): prefixo (um é início do outro) — cobre truncamentos
    # e pequenas variações de redação. Mínimo de 8 chars para evitar ruído.
    if not casadas and len(alvo) >= 8:
        casadas = [
            d for d in todas
            if (nd := normalizar_para_match(d.nome))
            and len(nd) >= 8
            and (nd.startswith(alvo) or alvo.startswith(nd))
        ]

    if not casadas:
        _registrar_auditoria(
            db,
            f"GET /aulas-por-disciplina disc={disciplina} (sem match)",
            _get_client_ip(request),
        )
        return AulasPorDisciplinaResponse(
            disciplina_consultada=disciplina, disciplina_casada=None, total=0, linhas=[]
        )

    disc_ids = [d.id for d in casadas]
    reports_q = db.query(ClassReport).filter(
        ClassReport.disciplina_id.in_(disc_ids),
        ClassReport.is_deleted.is_(False),
        ClassReport.nome_ficheiro_gerado.isnot(None),
    )
    if modalidade_filtro:
        reports_q = reports_q.join(Turma, ClassReport.turma_id == Turma.id).filter(
            func.upper(Turma.modalidade) == modalidade_filtro
        )
    reports = reports_q.order_by(ClassReport.data_aula).all()

    linhas = [
        AulaLinha(
            nome_arquivo=r.nome_ficheiro_gerado,
            vimeo_url=r.vimeo_link or "",
            drive_url=r.video_link or "",
            pdf_url=r.slide_link or "",
        )
        for r in reports
    ]

    audit_modalidade = f" mod={modalidade_filtro}" if modalidade_filtro else ""
    _registrar_auditoria(
        db,
        f"GET /aulas-por-disciplina disc={disciplina}{audit_modalidade} "
        f"casada={casadas[0].nome} total={len(linhas)}",
        _get_client_ip(request),
    )

    return AulasPorDisciplinaResponse(
        disciplina_consultada=disciplina,
        disciplina_casada=casadas[0].nome,
        total=len(linhas),
        linhas=linhas,
    )


# ─── Uso de estúdio (sistema de cobrança) — reunião 26/10/2026 ─────────


@router.get("/uso-estudio", summary="Uso de estúdio com o tempo exato de cada uso")
def uso_de_estudio(
    request: Request,
    data_inicio: date = Query(..., description="Início do período (data do uso)"),
    data_fim: date = Query(..., description="Fim do período (data do uso)"),
    estudio: Optional[str] = Query(None, description="Filtra por estúdio"),
    seduc: Optional[bool] = Query(None, description="true = só pedidos da SEDUC; false = só os outros"),
    tipo_uso: Optional[str] = Query(None, description="Aula, Gravação, Gravação antecipada, Reposição, Exibição de aula antecipada, Evento"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_external_token),
):
    """
    Um registro por uso do estúdio (relatórios finalizados), com início, fim e os
    **minutos exatos** de uso (07:30–10:15 = 165 min = 2h45). Não quebra em horas:
    a quebra por hora existe só na planilha Excel. `minutos_cobrados` é 0 quando o uso
    não é cobrado (gravação antecipada sem pedido da SEDUC: cobra só a exibição).
    """
    from app.services.audit_export import AuditExportFilters
    from app.services.uso_estudio import montar_usos, uso_para_api

    if data_inicio > data_fim:
        raise HTTPException(status_code=422, detail="data_inicio não pode ser maior que data_fim")
    if (data_fim - data_inicio).days > 366:
        raise HTTPException(status_code=422, detail="Período máximo de 1 ano por consulta.")

    filtros = AuditExportFilters(data_inicio=data_inicio, data_fim=data_fim, estudio=estudio)
    usos = [uso_para_api(u) for u in montar_usos(db, filtros)]
    if seduc is not None:
        usos = [u for u in usos if u["seduc"] == seduc]
    if tipo_uso:
        alvo = normalizar_para_match(tipo_uso)
        usos = [u for u in usos if normalizar_para_match(u["tipo_uso"]) == alvo]

    _registrar_auditoria(
        db,
        f"GET /uso-estudio {data_inicio}..{data_fim} estudio={estudio or '*'} total={len(usos)}",
        _get_client_ip(request),
    )
    return {
        "data_inicio": data_inicio.isoformat(),
        "data_fim": data_fim.isoformat(),
        "total_usos": len(usos),
        "minutos_uso": sum(u["minutos_uso"] or 0 for u in usos),
        "minutos_cobrados": sum(u["minutos_cobrados"] for u in usos),
        "usos": usos,
    }
