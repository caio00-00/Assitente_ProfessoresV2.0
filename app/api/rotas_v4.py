"""
Canal Educação v4 — Painel "Início", linha do tempo da aula e histórico de versões.

São rotas só de leitura que juntam o que já existe:
- /api/v1/painel/inicio            o que precisa da ação de quem está logado
- /api/v1/aulas/linha-do-tempo     uma aula de ponta a ponta (assistente,
                                   diretor, Drive, validações, faturamento)
- /api/v1/historico/{tipo}/{id}    versões de um relatório
"""

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.domain import estados, politicas
from app.models.class_report import ClassReport
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import ImageDirectorReport
from app.models.user import User
from app.services.historico import TIPO_AULA, TIPO_IMAGEM, listar_versoes

router = APIRouter(prefix="/api/v1", tags=["v4 — Painel e linha do tempo"])

LIMITE_ITENS = 15


# ─── Formatação ───────────────────────────────────────────────────────

def _d(v):
    return v.isoformat() if v else None


def _nome_turma(r) -> str:
    t = getattr(r, "turma", None)
    if t is not None:
        return t.nomenclatura_padrao or t.nome or ""
    return getattr(r, "serie_modulo_manual", None) or ""


def _nome_disciplina(r) -> str:
    d = getattr(r, "disciplina", None)
    return (d.nome if d is not None else None) or getattr(r, "disciplina_nome", None) or ""


def _item_aula(r: ClassReport) -> dict:
    return {
        "tipo": TIPO_AULA,
        "id": str(r.id),
        "data": _d(r.data_aula),
        "turma": _nome_turma(r),
        "disciplina": _nome_disciplina(r),
        "horario": r.horario_aula,
        "estudio": r.estudio,
        "status": r.status,
        "compliance": r.status_compliance,
        "precisa_correcao": bool(r.precisa_correcao),
        "observacao_coordenacao": r.observacao_coordenacao,
        "tem_video": bool((r.video_link or "").strip()),
        "tem_pdf": bool((r.slide_link or "").strip()),
    }


def _item_imagem(r: ImageDirectorReport) -> dict:
    corrompido = any((a.video_corrompido or "") == "Sim" for a in (r.lessons or []))
    return {
        "tipo": TIPO_IMAGEM,
        "id": str(r.id),
        "data": _d(r.data_relatorio),
        "turma": _nome_turma(r),
        "disciplina": _nome_disciplina(r),
        "turno": r.turno,
        "estudio": r.estudio,
        "status": r.status,
        "precisa_correcao": bool(r.precisa_correcao),
        "observacao_coordenacao": r.observacao_coordenacao,
        "video_corrompido": corrompido,
        "aulas": len(r.lessons or []),
    }


def _grupo(titulo: str, descricao: str, itens: list, acao: str, cor: str) -> dict:
    return {
        "titulo": titulo,
        "descricao": descricao,
        "total": len(itens),
        "itens": itens[:LIMITE_ITENS],
        "acao": acao,
        "cor": cor,  # verde | amarelo | vermelho | azul | cinza
    }


# ─── Painel Início ────────────────────────────────────────────────────

@router.get("/painel/inicio")
def painel_inicio(
    dias: int = Query(45, ge=1, le=365, description="Janela de datas de aula/relatório"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """O que precisa de quem está logado, por papel, nos últimos `dias`."""
    papel = politicas.normalizar_papel(user.role)
    desde = date.today() - timedelta(days=dias)
    grupos = []

    def aulas(*filtros):
        return (
            db.query(ClassReport)
            .filter(ClassReport.is_deleted == False, ClassReport.data_aula >= desde, *filtros)  # noqa: E712
            .order_by(ClassReport.data_aula.desc())
            .limit(200)
            .all()
        )

    def imagens(*filtros):
        return (
            db.query(ImageDirectorReport)
            .filter(ImageDirectorReport.is_deleted == False, ImageDirectorReport.data_relatorio >= desde, *filtros)  # noqa: E712
            .order_by(ImageDirectorReport.data_relatorio.desc())
            .limit(200)
            .all()
        )

    sem_link = or_(ClassReport.video_link.is_(None), ClassReport.slide_link.is_(None),
                   ClassReport.video_link == "", ClassReport.slide_link == "")
    finalizados = ClassReport.status.in_(tuple(estados.STATUS_FINALIZADOS))

    if papel == politicas.ASSISTENTE:
        meus = ClassReport.created_by == user.id
        grupos.append(_grupo("Devolvidos para corrigir", "A coordenação pediu correção. Ajuste e finalize de novo.",
                             [_item_aula(r) for r in aulas(meus, ClassReport.status == estados.RASCUNHO,
                                                           ClassReport.precisa_correcao == True)],  # noqa: E712
                             "corrigir", "vermelho"))
        grupos.append(_grupo("Rascunhos", "Relatórios salvos que ainda não foram finalizados.",
                             [_item_aula(r) for r in aulas(meus, ClassReport.status == estados.RASCUNHO,
                                                           ClassReport.precisa_correcao == False)],  # noqa: E712
                             "finalizar", "amarelo"))
        grupos.append(_grupo("Esperando vídeo e PDF no Drive", "Finalizados; a busca automática ainda não achou os arquivos.",
                             [_item_aula(r) for r in aulas(meus, finalizados, sem_link)],
                             "acompanhar", "azul"))
        grupos.append(_grupo("Validados", "Conferidos pela coordenação.",
                             [_item_aula(r) for r in aulas(meus, ClassReport.status == estados.VALIDADO)],
                             "ver", "verde"))

    if papel in (politicas.ADMIN, politicas.GESTOR, politicas.COORDENADOR, politicas.AUDITOR):
        com_link = ~sem_link
        grupos.append(_grupo("Prontos para validar", "Vídeo e PDF coletados no Drive.",
                             [_item_aula(r) for r in aulas(ClassReport.status.in_((estados.AGUARDANDO, estados.FINALIZADO_LEGADO)), com_link)],
                             "validar", "verde"))
        grupos.append(_grupo("Na fila, esperando o Drive", "Finalizados, mas ainda sem vídeo ou PDF.",
                             [_item_aula(r) for r in aulas(ClassReport.status.in_((estados.AGUARDANDO, estados.FINALIZADO_LEGADO)), sem_link)],
                             "acompanhar", "azul"))
        grupos.append(_grupo("Vermelhos no Drive", "A busca desistiu depois de 20 tentativas. Confira o nome do arquivo e use Reverificar.",
                             [_item_aula(r) for r in aulas(finalizados, ClassReport.status_compliance == "Vermelho")],
                             "reverificar", "vermelho"))
        grupos.append(_grupo("Devolvidos ao assistente", "Esperando o assistente corrigir.",
                             [_item_aula(r) for r in aulas(ClassReport.status == estados.RASCUNHO,
                                                           ClassReport.precisa_correcao == True)],  # noqa: E712
                             "acompanhar", "amarelo"))

    if papel == politicas.DIRETOR_IMAGEM:
        meu = db.query(DiretorImagem).filter(DiretorImagem.user_id == user.id).first()
        if meu:
            meus = ImageDirectorReport.diretor_imagem_id == meu.id
            todos = imagens(meus)
            grupos.append(_grupo("Devolvidos para corrigir", "O diretor-chefe pediu correção.",
                                 [_item_imagem(r) for r in todos if r.status == estados.RASCUNHO and r.precisa_correcao], "corrigir", "vermelho"))
            grupos.append(_grupo("Vídeo marcado como corrompido", "Enquanto estiver marcado, o vídeo não é buscado e o relatório não é validado.",
                                 [i for i in map(_item_imagem, todos) if i["video_corrompido"] and i["status"] != estados.CANCELADO], "corrigir", "vermelho"))
            grupos.append(_grupo("Rascunhos", "Turnos ainda não finalizados. A busca do vídeo só começa quando você finaliza.",
                                 [_item_imagem(r) for r in todos if r.status == estados.RASCUNHO and not r.precisa_correcao], "finalizar", "amarelo"))
            grupos.append(_grupo("Aguardando o diretor-chefe", "Finalizados, na fila de validação.",
                                 [_item_imagem(r) for r in todos if r.status in (estados.AGUARDANDO, estados.FINALIZADO_LEGADO)], "acompanhar", "azul"))

    if papel in (politicas.DIRETOR_CHEFE, politicas.ADMIN, politicas.GESTOR):
        todos = imagens()
        grupos.append(_grupo("Relatórios de imagem para validar", "Finalizados pelos diretores.",
                             [_item_imagem(r) for r in todos if r.status in (estados.AGUARDANDO, estados.FINALIZADO_LEGADO)
                              and not any((a.video_corrompido or "") == "Sim" for a in (r.lessons or []))], "validar", "verde"))
        grupos.append(_grupo("Vídeo corrompido", "Validação travada até o diretor recuperar o vídeo.",
                             [i for i in map(_item_imagem, todos) if i["video_corrompido"] and i["status"] != estados.CANCELADO], "acompanhar", "vermelho"))

    return {
        "usuario": {"nome": user.full_name, "papel": papel},
        "desde": desde.isoformat(),
        "dias": dias,
        "grupos": grupos,
    }


# ─── Linha do tempo da aula ───────────────────────────────────────────

def _pode_ver_aula(db: Session, user: User, cr: Optional[ClassReport], idr: Optional[ImageDirectorReport]) -> bool:
    if politicas.pode(user, "aula.linha_do_tempo"):
        return True
    papel = politicas.normalizar_papel(user.role)
    if papel == politicas.ASSISTENTE and cr is not None and str(cr.created_by) == str(user.id):
        return True
    if papel == politicas.DIRETOR_IMAGEM and idr is not None:
        meu = db.query(DiretorImagem).filter(DiretorImagem.user_id == user.id).first()
        return bool(meu and meu.id == idr.diretor_imagem_id)
    return False


def _etapa(chave, titulo, estado, detalhe, quando=None, quem=None):
    # estado: ok | atencao | pendente | bloqueado | nao_se_aplica
    return {"chave": chave, "titulo": titulo, "estado": estado, "detalhe": detalhe, "quando": quando, "quem": quem}


def _nome_usuario(db: Session, user_id) -> Optional[str]:
    if not user_id:
        return None
    u = db.query(User).filter(User.id == user_id).first()
    return u.full_name if u else None


def _versoes_json(db: Session, tipo: str, report_id) -> list:
    saida = []
    for v in listar_versoes(db, tipo, report_id):
        alteracoes = v.alteracoes or {}
        saida.append({
            "versao": v.versao,
            "evento": v.evento,
            "status_anterior": v.status_anterior,
            "status_novo": v.status_novo,
            "motivo": v.motivo,
            "quem": _nome_usuario(db, v.alterado_por),
            "quando": v.alterado_em.isoformat() if v.alterado_em else None,
            "campos_alterados": sorted(k for k in alteracoes.keys() if not k.startswith("_") and k != "updated_at"),
        })
    return saida


@router.get("/aulas/linha-do-tempo")
def linha_do_tempo(
    class_report_id: Optional[UUID] = Query(None),
    image_director_report_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Uma aula de ponta a ponta. Informe o id do relatório de aula ou do relatório de imagem."""
    from app.services.audit_export import classificar_lancamento, cobrar_conforme_status
    from app.services.busca_links import bloqueio_busca_link, class_reports_do_idr, motivo_espera_validacao
    from app.services.image_director_associacao import (
        buscar_image_director_por_class_report,
        divergencias_do_par,
    )

    if not class_report_id and not image_director_report_id:
        raise HTTPException(status_code=422, detail="Informe class_report_id ou image_director_report_id.")

    cr = idr = None
    if class_report_id:
        cr = db.query(ClassReport).filter(ClassReport.id == class_report_id).first()
        if not cr:
            raise HTTPException(status_code=404, detail="Relatório de aula não encontrado.")
        idr = buscar_image_director_por_class_report(db, cr)
    else:
        idr = db.query(ImageDirectorReport).filter(ImageDirectorReport.id == image_director_report_id).first()
        if not idr:
            raise HTTPException(status_code=404, detail="Relatório de imagem não encontrado.")
        ligados = class_reports_do_idr(db, idr)
        cr = ligados[0] if ligados else None

    if not _pode_ver_aula(db, user, cr, idr):
        raise HTTPException(status_code=403, detail="Sem permissão para ver esta aula.")

    etapas = []
    # 1. Relatório do assistente
    if cr is None:
        etapas.append(_etapa("assistente", "Relatório do assistente", "pendente", "Ainda não há relatório de aula ligado a este turno."))
    else:
        est = {"RASCUNHO": "pendente", "CANCELADO": "bloqueado"}.get(cr.status, "ok")
        det = {"RASCUNHO": "Rascunho" + (" — devolvido para correção" if cr.precisa_correcao else ""),
               "CANCELADO": f"Cancelado: {cr.justificativa_cancelamento or cr.observacoes or 'sem justificativa'}"}.get(
            cr.status, f"Finalizado ({cr.status.replace('_', ' ').lower()})")
        etapas.append(_etapa("assistente", "Relatório do assistente", est, det,
                             quem=_nome_usuario(db, cr.created_by)))
    # 2. Relatório do diretor
    if idr is None:
        etapas.append(_etapa("diretor", "Relatório do diretor de imagem", "pendente" if cr else "nao_se_aplica",
                             "Nenhum relatório de imagem ligado a esta aula."))
    else:
        corrompido = any((a.video_corrompido or "") == "Sim" for a in (idr.lessons or []))
        est = "bloqueado" if corrompido else {"RASCUNHO": "pendente", "CANCELADO": "bloqueado"}.get(idr.status, "ok")
        det = "Vídeo marcado como corrompido" if corrompido else {
            "RASCUNHO": "Rascunho — a busca do vídeo espera o diretor finalizar",
            "CANCELADO": "Cancelado"}.get(idr.status, f"Finalizado ({idr.status.replace('_', ' ').lower()})")
        etapas.append(_etapa("diretor", "Relatório do diretor de imagem", est, det,
                             quem=idr.diretor_imagem.nome if idr.diretor_imagem else None))
    # 3. Par
    if cr and idr:
        diverg = divergencias_do_par(cr, idr)
        ligado_direto = str(idr.class_report_id or "") == str(cr.id) or any(
            str(a.class_report_id or "") == str(cr.id) for a in (idr.lessons or []))
        etapas.append(_etapa("par", "Os dois relatórios conferem",
                             "atencao" if diverg else "ok",
                             "; ".join(diverg) if diverg else
                             ("Vinculados diretamente." if ligado_direto else "Par encontrado pela grade/YouTube (não vinculado diretamente).")))
    # 4. Drive
    if cr is not None and cr.status in estados.STATUS_FINALIZADOS:
        bloqueio = bloqueio_busca_link(db, cr)
        if (cr.video_link or "").strip() and (cr.slide_link or "").strip():
            etapas.append(_etapa("drive", "Vídeo e PDF no Drive", "ok", "Os dois arquivos foram encontrados."))
        elif bloqueio:
            etapas.append(_etapa("drive", "Vídeo e PDF no Drive", "bloqueado", bloqueio))
        else:
            etapas.append(_etapa("drive", "Vídeo e PDF no Drive",
                                 "bloqueado" if cr.status_compliance == "Vermelho" else "pendente",
                                 motivo_espera_validacao(cr, idr) or cr.status_compliance))
    else:
        etapas.append(_etapa("drive", "Vídeo e PDF no Drive", "nao_se_aplica", "A busca começa quando o relatório de aula é finalizado."))
    # 5. Validação da aula
    if cr is not None:
        if cr.status == estados.VALIDADO:
            etapas.append(_etapa("validacao_aula", "Validação da coordenação", "ok", "Validado.",
                                 quando=_d(cr.validado_em), quem=_nome_usuario(db, cr.validado_por)))
        elif cr.status == estados.CANCELADO:
            etapas.append(_etapa("validacao_aula", "Validação da coordenação", "nao_se_aplica", "Cancelado."))
        else:
            etapas.append(_etapa("validacao_aula", "Validação da coordenação", "pendente",
                                 motivo_espera_validacao(cr, idr) or "Pronto para validar."))
    # 6. Validação do diretor-chefe
    if idr is not None:
        if idr.status == estados.VALIDADO:
            etapas.append(_etapa("validacao_imagem", "Validação do diretor-chefe", "ok", "Validado.",
                                 quando=_d(idr.validado_em), quem=_nome_usuario(db, idr.validado_por)))
        elif idr.status == estados.CANCELADO:
            etapas.append(_etapa("validacao_imagem", "Validação do diretor-chefe", "nao_se_aplica", "Cancelado."))
        else:
            etapas.append(_etapa("validacao_imagem", "Validação do diretor-chefe", "pendente", "Aguardando validação."))
    # 7. Faturamento
    lancamento, cobrar_regra = classificar_lancamento(cr, idr)
    cobrar = cobrar_conforme_status(cr, idr, cobrar_regra)
    etapas.append(_etapa("faturamento", "Faturamento", "ok" if not cobrar.startswith("Pendente") else "pendente",
                         f"{lancamento.title()} — cobrar: {cobrar}"))

    referencia = cr or idr
    return {
        "aula": {
            "data": _d(cr.data_aula if cr else idr.data_relatorio),
            "turma": _nome_turma(referencia),
            "disciplina": _nome_disciplina(referencia),
            "estudio": (cr.estudio if cr else idr.estudio),
            "turno": (cr.turno if cr else idr.turno),
            "horario": cr.horario_aula if cr else idr.horario_aula,
            "nome_arquivo": cr.nome_ficheiro_gerado if cr else None,
            "youtube": (cr.youtube_link if cr else None) or (idr.youtube_link if idr else None),
            "lancamento": lancamento,
            "cobrar": cobrar,
            "pedido_seduc": ((cr.solicitante_antecipacao if cr else None) or (idr.solicitante_antecipacao if idr else None)) == "SEDUC",
        },
        "relatorio_aula": None if cr is None else {
            **_item_aula(cr),
            "professor": (cr.professor.nome if cr.professor else cr.professor_nome_externo),
            "conteudo": cr.conteudo_ministrado,
            "video_link": cr.video_link,
            "slide_link": cr.slide_link,
            "vimeo_link": cr.vimeo_link,
            "data_gravacao": _d(cr.data_execucao_real),
            "data_referencia": _d(cr.data_referencia_aula),
            "motivo_referencia": cr.motivo_referencia,
        },
        "relatorio_imagem": None if idr is None else {
            **_item_imagem(idr),
            "diretor": idr.diretor_imagem.nome if idr.diretor_imagem else None,
            "aulas_detalhe": [
                {"numero": a.numero_aula, "disciplina": a.disciplina_nome, "professor": a.professor_nome,
                 "tipo": a.transmissao_ou_gravada, "video_corrompido": a.video_corrompido,
                 "chamado": a.numero_chamado}
                for a in sorted(idr.lessons or [], key=lambda x: x.numero_aula or 0)
            ],
        },
        "etapas": etapas,
        "versoes_aula": _versoes_json(db, TIPO_AULA, cr.id) if cr else [],
        "versoes_imagem": _versoes_json(db, TIPO_IMAGEM, idr.id) if idr else [],
    }


# ─── Histórico de versões ─────────────────────────────────────────────

@router.get("/historico/{tipo}/{report_id}")
def historico(
    tipo: str,
    report_id: UUID,
    incluir_snapshot: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    if tipo not in (TIPO_AULA, TIPO_IMAGEM):
        raise HTTPException(status_code=422, detail="tipo deve ser class_report ou image_director_report.")
    if tipo == TIPO_AULA:
        cr = db.query(ClassReport).filter(ClassReport.id == report_id).first()
        if not cr or not _pode_ver_aula(db, user, cr, None):
            raise HTTPException(status_code=404, detail="Relatório não encontrado.")
    else:
        idr = db.query(ImageDirectorReport).filter(ImageDirectorReport.id == report_id).first()
        if not idr or not _pode_ver_aula(db, user, None, idr):
            raise HTTPException(status_code=404, detail="Relatório não encontrado.")
    versoes = _versoes_json(db, tipo, report_id)
    if incluir_snapshot and politicas.pode(user, "aula.linha_do_tempo"):
        completas = listar_versoes(db, tipo, report_id)
        for v, c in zip(versoes, completas):
            v["snapshot"] = c.snapshot
            v["alteracoes"] = c.alteracoes
    return {"tipo": tipo, "report_id": str(report_id), "versoes": versoes}
