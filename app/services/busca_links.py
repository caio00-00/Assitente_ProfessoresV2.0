"""
Busca dos links (vídeo e PDF) no Drive x relatório do diretor de imagem.

Reunião (out/2026):
- quem diz se o vídeo está bom é o diretor de imagem. Enquanto ele marcar
  "vídeo corrompido = Sim", o sistema NÃO busca o link do vídeo (pegaria um
  arquivo quebrado que depois não dá para substituir). Ele recupera o vídeo
  (ou baixa do YouTube, corta e põe na pasta), desmarca e salva — aí a busca começa;
- a busca só começa depois que o diretor finaliza o relatório dele (aula sem relatório
  do diretor ligado segue como antes, para o link não ficar parado);
- o coordenador pedagógico só valida o relatório da aula quando os dois links
  (vídeo e PDF) já foram coletados;
- o diretor-chefe não valida o relatório de imagem com vídeo marcado como corrompido.
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.class_report import ClassReport
from app.models.image_director_report import ImageDirectorReport

STATUS_IDR_FINALIZADOS = ("AGUARDANDO_VALIDACAO", "VALIDADO", "FINALIZADO")
STATUS_CR_FINALIZADOS = ("FINALIZADO", "AGUARDANDO_VALIDACAO", "VALIDADO")

AGUARDANDO_DIRETOR = "Aguardando o relatório do diretor de imagem"
AGUARDANDO_FINALIZAR = "Aguardando o diretor de imagem finalizar o relatório"
VIDEO_CORROMPIDO = "Vídeo marcado como corrompido pelo diretor de imagem"


def _lessons_da_aula(idr: ImageDirectorReport, cr: Optional[ClassReport]) -> list:
    lessons = list(idr.lessons or [])
    if cr is not None:
        da_aula = [l for l in lessons if l.class_report_id == cr.id]
        if da_aula:
            return da_aula
    return lessons


def video_corrompido(idr: Optional[ImageDirectorReport], cr: Optional[ClassReport] = None) -> bool:
    """O diretor marcou 'vídeo corrompido = Sim' em alguma aula (a desta aula, se ligada)."""
    if idr is None:
        return False
    return any((l.video_corrompido or "").strip().lower() == "sim" for l in _lessons_da_aula(idr, cr))


def bloqueio_busca_link(db: Session, cr: ClassReport, *, exigir_diretor: bool = True) -> Optional[str]:
    """
    None = pode buscar os links no Drive. Senão, o motivo da espera.
    `exigir_diretor=False` (botão "Reverificar" da coordenação): aula sem relatório do
    diretor pode buscar; vídeo corrompido continua bloqueando.
    """
    from app.services.image_director_associacao import buscar_image_director_por_class_report

    idr = buscar_image_director_por_class_report(db, cr)
    if idr is None:
        # Aula sem relatório do diretor ligado (aula antiga, sem diretor escalado…): segue a
        # regra de antes para não deixar o link parado para sempre. Quando o diretor abrir o
        # relatório dele, a busca passa a esperar ele finalizar.
        return None
    if idr.status not in STATUS_IDR_FINALIZADOS:
        return AGUARDANDO_FINALIZAR if exigir_diretor else None
    if video_corrompido(idr, cr):
        return VIDEO_CORROMPIDO
    return None


def class_reports_do_idr(db: Session, idr: ImageDirectorReport) -> List[ClassReport]:
    """Relatórios de aula ligados ao relatório do diretor (direto, pelas aulas ou pelo par)."""
    ids = {idr.class_report_id} | {l.class_report_id for l in (idr.lessons or [])}
    ids.discard(None)
    crs = []
    if ids:
        crs = db.query(ClassReport).filter(
            ClassReport.id.in_(list(ids)), ClassReport.is_deleted == False  # noqa: E712
        ).all()
    if not crs:
        from app.services.image_director_associacao import _match_por_caracteristicas, _match_por_grade

        cr = _match_por_grade(db, idr) or _match_por_caracteristicas(db, idr)
        crs = [cr] if cr else []
    return crs


def disparar_busca_apos_diretor(db: Session, idr: ImageDirectorReport) -> int:
    """
    O diretor finalizou (ou desmarcou o vídeo corrompido e salvou): começa a busca
    dos links das aulas ligadas que ainda não têm vídeo/PDF. Devolve quantas foram enfileiradas.
    """
    if idr.status not in STATUS_IDR_FINALIZADOS:
        return 0
    enfileiradas = 0
    for cr in class_reports_do_idr(db, idr):
        if cr.status not in STATUS_CR_FINALIZADOS or not cr.nome_ficheiro_gerado:
            continue
        if cr.video_link and cr.slide_link:
            continue
        if video_corrompido(idr, cr):
            continue
        try:
            from app.services.tarefas import modo, verificar_agora

            if modo() == "direto":
                # v4.1 (sem worker): não busca na hora para não atrasar o diretor;
                # a próxima varredura pega estes relatórios.
                continue
            verificar_agora(cr.id, cr.nome_ficheiro_gerado)
            enfileiradas += 1
        except Exception as e:  # fila fora do ar: a varredura periódica pega depois
            print(f"[BUSCA_LINKS] não foi possível enfileirar {cr.id}: {e}")
    return enfileiradas


def links_coletados(cr: ClassReport) -> bool:
    return bool((cr.video_link or "").strip() and (cr.slide_link or "").strip())


def motivo_espera_validacao(cr: ClassReport, idr: Optional[ImageDirectorReport]) -> Optional[str]:
    """
    Fila da coordenação: None = pronto para validar (vídeo e PDF coletados).
    Senão, o que falta, na língua de quem está esperando.
    """
    if links_coletados(cr):
        return None
    faltam = [n for n, v in (("vídeo", cr.video_link), ("PDF", cr.slide_link)) if not (v or "").strip()]
    base = "Aguardando o link do " + " e do ".join(faltam)
    if idr is not None:
        if video_corrompido(idr, cr):
            return f"{base} — {VIDEO_CORROMPIDO.lower()}"
        if idr.status not in STATUS_IDR_FINALIZADOS:
            return f"{base} — {AGUARDANDO_FINALIZAR.lower()}"
    return f"{base} (busca automática no Drive)"
