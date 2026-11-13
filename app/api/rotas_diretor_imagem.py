"""
Canal Educação v3.2 — Rotas do Relatório do Diretor de Imagem.

Tela restrita ao papel `diretor_imagem` (e `diretor_chefe`/`admin`/`gestor`
com visão completa), parecida com a tela de Relatório de Aula, mas para o
acompanhamento técnico do turno no estúdio: cabeçalho automático + lista de
aulas (puxadas do relatório de aula já lançado, com opção manual) + checklist
de fechamento de estúdio + perguntas extras cadastradas pelo Diretor-Chefe +
exportação em PDF.
"""

from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_active_user, require_role
from app.core.database import get_db
from app.domain import estados
from app.domain.enums.enums import PAPEIS_DIRETOR_CHEFE, PAPEIS_DIRETOR_IMAGEM
from app.services.historico import TIPO_IMAGEM, registrar_versao
from app.models.auxiliares import Disciplina, Professor, ProfessorDisciplina
from app.models.audit_log import AuditLog
from app.models.class_report import ClassReport
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import (
    ImageDirectorChecklistItem,
    ImageDirectorChecklistResponse,
    ImageDirectorCustomAnswer,
    ImageDirectorCustomQuestion,
    ImageDirectorLesson,
    ImageDirectorReport,
)
from app.models.user import User
from app.schemas.image_director_report import (
    ChecklistAnswerIn,
    ChecklistItemCreate,
    ChecklistItemResponse,
    ChecklistItemUpdate,
    CustomAnswerIn,
    CustomAnswerResponse,
    CustomQuestionCreate,
    CustomQuestionResponse,
    CustomQuestionUpdate,
    ImageDirectorLessonCreate,
    ImageDirectorLessonResponse,
    ExistingReportLookup,
    ImageDirectorReportCreate,
    ImageDirectorReportListItem,
    ImageDirectorReportResponse,
    ImageDirectorReportUpdate,
    ImageDirectorFinalizeRequest,
    ImageDirectorSolicitarCorrecao,
    NumeroAulaLookup,
    PaginatedImageDirectorReports,
)
from app.services.image_director_associacao import (
    associar_class_report,
    divergencias_do_par,
    validar_consistencia_faturamento,
    gerar_indicativo_reposicao,
    _match_por_grade,
    _match_por_caracteristicas,
)
from app.services.image_director_pdf import render_report_pdf, render_turno_pdf
from app.services.image_director_slot import (
    _is_ti_turma,
    compute_numero_aula_slot,
    find_existing_report_by_slot,
    list_horario_options,
    report_pertence_grade,
    resolve_slot_ordinal,
    resolve_slot_times,
)
from app.models.turma import Turma
from app.services.horario_resolver import format_faixa
from app.services.idr_txt_parser import norm_estudio, norm_key, norm_turno
from app.services.filtros import (
    disciplina_equivalentes,
    estudio_variantes,
    professor_equivalentes,
    valores_equivalentes,
)

router = APIRouter(prefix="/api/v1/image-director", tags=["Relatório do Diretor de Imagem"])


def _apply_slot_times_from_horario(db: Session, report: ImageDirectorReport) -> None:
    """
    Preenche start_time/end_time (HH:MM exatos) a partir do slot:
    grade real da turma no dia (por turno/modalidade) → tabela padrão.
    """
    if not report.horario_aula or (report.regular or "Sim") != "Sim":
        return
    st, et = resolve_slot_times(
        db,
        turma_id=report.turma_id,
        data=report.data_relatorio,
        turno=report.turno,
        horario_aula=report.horario_aula,
    )
    if st and et:
        report.start_time = st
        report.end_time = et


def _slot_times_for_display(
    db: Session,
    report: ImageDirectorReport,
    cache: Optional[dict] = None,
):
    """(início, fim) para exibição — usa o persistido ou resolve na hora (legado)."""
    if report.start_time and report.end_time:
        return report.start_time, report.end_time
    if (report.regular or "Sim") != "Sim":
        return report.start_time, report.end_time
    st, et = resolve_slot_times(
        db,
        turma_id=report.turma_id,
        data=report.data_relatorio,
        turno=report.turno,
        horario_aula=report.horario_aula,
        cache=cache,
    )
    return st or report.start_time, et or report.end_time


def _attach_display_times(db: Session, reports: list, cache: Optional[dict] = None) -> None:
    """Anexa `_slot_times` (transiente, não persistido) para o PDF."""
    cache = cache if cache is not None else {}
    for r in reports:
        r._slot_times = _slot_times_for_display(db, r, cache)
        r._slot_ordinal = (
            resolve_slot_ordinal(
                db,
                turma_id=r.turma_id,
                data=r.data_relatorio,
                turno=r.turno,
                horario_aula=r.horario_aula,
                start_time=r._slot_times[0],
                cache=cache,
            )
            if (r.regular or "Sim") == "Sim"
            else None
        )


TURNO_DB_VARIANTS = {
    "Manhã": ["Manhã", "MANHÃ", "MANHA", "Manha", "manha"],
    "Tarde": ["Tarde", "TARDE", "tarde"],
    "Noite": ["Noite", "NOITE", "noite"],
    "FDS manhã": ["FDS manhã", "FDS MANHÃ", "FDS MANHA", "FDS manha"],
    "FDS tarde": ["FDS tarde", "FDS TARDE"],
    "FDS noite": ["FDS noite", "FDS NOITE"],
    "Outro": ["Outro", "OUTRO"],
}


def _turno_filter_variants(turno: str) -> List[str]:
    """Variantes de turno gravadas no banco para o valor canônico do filtro."""
    raw = (turno or "").strip()
    if not raw:
        return []
    key = norm_key(raw)
    if key.startswith("FDS"):
        if "MANHA" in key:
            return TURNO_DB_VARIANTS["FDS manhã"]
        if "TARDE" in key:
            return TURNO_DB_VARIANTS["FDS tarde"]
        if "NOITE" in key:
            return TURNO_DB_VARIANTS["FDS noite"]
    canonical = norm_turno(raw)
    if canonical in TURNO_DB_VARIANTS:
        return TURNO_DB_VARIANTS[canonical]
    return [raw]


# ─── Helpers de permissão ───────────────────────────────────────────────

def _get_own_diretor_imagem(db: Session, user: User) -> Optional[DiretorImagem]:
    return db.query(DiretorImagem).filter(DiretorImagem.user_id == user.id).first()


def _resolve_diretor_imagem_id(
    db: Session,
    user: User,
    payload_diretor_id: Optional[UUID],
) -> UUID:
    """Diretor comum usa cadastro vinculado; chefe/admin/gestor escolhem no formulário."""
    if user.role in PAPEIS_DIRETOR_CHEFE:
        if not payload_diretor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe o Diretor de Imagem.",
            )
        diretor = (
            db.query(DiretorImagem)
            .filter(
                DiretorImagem.id == payload_diretor_id,
                DiretorImagem.is_active == True,  # noqa: E712
            )
            .first()
        )
        if not diretor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diretor de Imagem não encontrado ou inativo.",
            )
        return diretor.id

    own = _get_own_diretor_imagem(db, user)
    if not own:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu usuário não está vinculado a um cadastro de Diretor de Imagem.",
        )
    return own.id


def _assert_can_manage(db: Session, user: User, report: ImageDirectorReport):
    """Garante que o usuário pode ver/editar este relatório."""
    if user.role in PAPEIS_DIRETOR_CHEFE:
        return
    own = _get_own_diretor_imagem(db, user)
    if not own or own.id != report.diretor_imagem_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você só pode acessar os seus próprios relatórios.",
        )


def _assert_can_modify(report: ImageDirectorReport, user: Optional[User] = None) -> bool:
    """
    Paridade com o Relatório de Aula.
    - CANCELADO: não pode ser alterado.
    - VALIDADO (v4): só diretor-chefe/gestão alteram, e o relatório volta para
      a fila de validação (antes qualquer diretor alterava e ele seguia VALIDADO).
    Devolve True quando a alteração reabriu um relatório validado.
    """
    if report.status == estados.CANCELADO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Relatório cancelado não pode ser editado.",
        )
    if report.status == estados.VALIDADO:
        if user is None or user.role not in PAPEIS_DIRETOR_CHEFE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este relatório já foi validado. Para alterar, peça ao diretor-chefe para devolvê-lo.",
            )
        report.status = estados.destino("reabrir", report.status)
        report.validado_por = None
        report.validado_em = None
        return True
    return False


def _versionar_se_finalizado(db: Session, report: ImageDirectorReport, user: User, reaberto: bool,
                             status_anterior: Optional[str]) -> None:
    """Grava versão de alterações feitas depois da finalização (rascunho não gera histórico a cada clique)."""
    if reaberto or (status_anterior and status_anterior != estados.RASCUNHO):
        registrar_versao(db, TIPO_IMAGEM, report, "REABERTO" if reaberto else "EDITADO", user,
                         status_anterior=status_anterior)


def _pdf_filename(report: ImageDirectorReport) -> str:
    data_fmt = report.data_relatorio.strftime("%d-%m-%Y")
    estudio = (
        report.estudio.upper()
        .replace(" ", "_")
        .replace("Ú", "U")
        .replace("É", "E")
        .replace("Ó", "O")
        .replace("Í", "I")
        .replace("Á", "A")
        .replace("Ã", "A")
        .replace("Ç", "C")
    )
    estudio = estudio.replace("ESTÚDIO", "ESTUDIO")

    serie = report.turma_nome
    if not serie or serie == "N/A":
        serie = report.serie_modulo_manual or "SEM_TURMA"
    serie_slug = (
        serie.upper()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_")
    )

    return f"AULAS {data_fmt} {estudio} {serie_slug}.pdf"


def _get_report_or_404(db: Session, report_id: UUID) -> ImageDirectorReport:
    report = (
        db.query(ImageDirectorReport)
        .options(
            joinedload(ImageDirectorReport.lessons).joinedload(ImageDirectorLesson.respostas_extras),
            joinedload(ImageDirectorReport.checklist_respostas).joinedload(
                ImageDirectorChecklistResponse.item
            ),
            joinedload(ImageDirectorReport.respostas_extras).joinedload(
                ImageDirectorCustomAnswer.question
            ),
        )
        .filter(ImageDirectorReport.id == report_id, ImageDirectorReport.is_deleted == False)  # noqa: E712
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")
    return report


# ─── Lookups (auto-preenchimento) ───────────────────────────────────────

@router.get("/lookup/diretores")
def lookup_diretores(
    proprio: bool = Query(False, description="Se true, retorna apenas o diretor vinculado ao usuário logado"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    """
    Lista de diretores de imagem selecionáveis.
    Com `proprio=true` (formulário): só o cadastro vinculado ao usuário logado,
    exibindo o nome do usuário — sem opção de lançar em nome de outro diretor.
    Sem o parâmetro (filtros do histórico): chefe/admin/gestor veem todos.
    """
    if proprio or current_user.role not in PAPEIS_DIRETOR_CHEFE:
        own = _get_own_diretor_imagem(db, current_user)
        if not own:
            return []
        nome = (current_user.full_name or own.nome or "").strip() or own.nome
        return [{"id": str(own.id), "nome": nome}]

    diretores = (
        db.query(DiretorImagem)
        .filter(DiretorImagem.is_active == True)  # noqa: E712
        .order_by(DiretorImagem.nome)
        .all()
    )
    return [{"id": str(d.id), "nome": d.nome} for d in diretores]


@router.get("/lookup/turnos-do-dia")
def lookup_turnos_do_dia(
    data: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    """
    v3.2 — Lista os turnos/estúdios que já têm aulas lançadas (Relatório de
    Aula) numa data, para o diretor de imagem escolher a partir de opções
    reais do sistema em vez de digitar/selecionar às cegas — mesma lógica de
    auto-preenchimento do Relatório de Aula do assistente.
    """
    aulas = (
        db.query(ClassReport)
        .filter(
            ClassReport.data_aula == data,
            ClassReport.is_deleted == False,  # noqa: E712
        )
        .order_by(ClassReport.turno, ClassReport.estudio)
        .all()
    )
    vistos = set()
    opcoes = []
    for a in aulas:
        chave = (a.turno, a.estudio, str(a.turma_id) if a.turma_id else a.turma_nome)
        if chave in vistos:
            continue
        vistos.add(chave)
        opcoes.append({
            "turno": a.turno,
            "estudio": a.estudio,
            "turma_id": str(a.turma_id) if a.turma_id else None,
            "turma_nome": a.turma_nome,
        })
    return opcoes


@router.get("/lookup/aulas")
def lookup_aulas(
    data: date = Query(...),
    turno: str = Query(...),
    estudio: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    """
    Sugere as aulas já lançadas (Relatório de Aula) para o turno/estúdio/data
    informados, para auto-preencher os blocos "AULA 0X".
    """
    aulas = (
        db.query(ClassReport)
        .filter(
            ClassReport.data_aula == data,
            ClassReport.turno == turno,
            ClassReport.estudio == estudio,
            ClassReport.is_deleted == False,  # noqa: E712
        )
        .order_by(ClassReport.horario_aula)
        .all()
    )
    return [
        {
            "class_report_id": str(a.id),
            "disciplina_nome": a.disciplina_nome,
            "professor_nome": a.professor_nome,
            "horario_aula": a.horario_aula,
            "canal_utilizado": a.canal_utilizado,
            "turma_nome": a.turma_nome,
            "turma_id": str(a.turma_id) if a.turma_id else None,
        }
        for a in aulas
    ]


@router.get("/lookup/disciplinas")
def lookup_disciplinas(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    """Disciplinas ativas para preenchimento manual das aulas do turno."""
    disciplinas = (
        db.query(Disciplina)
        .filter(Disciplina.is_active == True)  # noqa: E712
        .order_by(Disciplina.nome)
        .all()
    )
    return [{"id": str(d.id), "nome": d.nome} for d in disciplinas]


@router.get("/lookup/professores")
def lookup_professores(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    """Professores ativos para preenchimento manual das aulas do turno."""
    professores = (
        db.query(Professor)
        .filter(Professor.is_active == True)  # noqa: E712
        .order_by(Professor.nome)
        .distinct(Professor.nome)
        .all()
    )
    return [{"id": str(p.id), "nome": p.nome} for p in professores]


@router.get("/lookup/professores-por-disciplina/{disciplina_id}")
def lookup_professores_por_disciplina(
    disciplina_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    """Professores vinculados à disciplina selecionada."""
    professores = (
        db.query(Professor)
        .join(ProfessorDisciplina)
        .filter(ProfessorDisciplina.disciplina_id == disciplina_id)
        .filter(Professor.is_active == True)  # noqa: E712
        .all()
    )
    unique = {p.id: p for p in professores}.values()
    return [{"id": str(p.id), "nome": p.nome} for p in sorted(unique, key=lambda x: x.nome)]


@router.get("/lookup/existing", response_model=Optional[ExistingReportLookup])
def lookup_existing_report(
    data: date = Query(...),
    turno: str = Query(...),
    estudio: str = Query(...),
    disciplina_id: Optional[UUID] = Query(None),
    diretor_imagem_id: Optional[UUID] = Query(None),
    class_report_id: Optional[UUID] = Query(None),
    turma_id: Optional[UUID] = Query(None),
    horario_aula: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    """
    Busca relatório existente por slot: class_report_id ou turma+horário.
    """
    diretor_id = diretor_imagem_id
    if current_user.role not in PAPEIS_DIRETOR_CHEFE:
        own = _get_own_diretor_imagem(db, current_user)
        if not own:
            return None
        diretor_id = own.id
    elif not diretor_id:
        return None

    report = find_existing_report_by_slot(
        db,
        diretor_id,
        data,
        turno,
        estudio,
        class_report_id=class_report_id,
        turma_id=turma_id,
        horario_aula=horario_aula,
        turno_variants=_turno_filter_variants(turno),
    )
    if report:
        return ExistingReportLookup(id=str(report.id), status=report.status)

    # Legado: só disciplina quando slot não informado
    if disciplina_id and not class_report_id and not horario_aula:
        q = db.query(ImageDirectorReport.id, ImageDirectorReport.status).filter(
            ImageDirectorReport.diretor_imagem_id == diretor_id,
            ImageDirectorReport.data_relatorio == data,
            ImageDirectorReport.turno.in_(_turno_filter_variants(turno) or [turno]),
            ImageDirectorReport.estudio == estudio,
            ImageDirectorReport.disciplina_id == disciplina_id,
            ImageDirectorReport.is_deleted == False,  # noqa: E712
        )
        row = q.first()
        if row:
            return ExistingReportLookup(id=str(row.id), status=row.status)

    return None


@router.get("/lookup/numero-aula", response_model=NumeroAulaLookup)
def lookup_numero_aula(
    turma_id: UUID = Query(...),
    data: date = Query(...),
    horario_aula: Optional[str] = Query(None),
    class_report_id: Optional[UUID] = Query(None),
    turno: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    """Número sequencial da aula conforme posição do slot na grade do dia."""
    numero = compute_numero_aula_slot(
        db,
        turma_id,
        data,
        horario_aula=horario_aula,
        class_report_id=class_report_id,
        report_turno=turno,
    )
    return NumeroAulaLookup(numero_aula=numero)


@router.get("/lookup/horarios")
def lookup_horarios(
    turma_id: Optional[UUID] = Query(None),
    data: Optional[date] = Query(None),
    turno: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    """
    Horários das disciplinas por turno e modalidade da turma, com HH:MM.

    Fonte primária: grade horária real da turma no dia (REGULAR reinicia a
    numeração por turno; TI é contínuo manhã → tarde; TECNICO/EJA usam os
    próprios horários cadastrados). Sem grade no dia, usa a tabela padrão.
    """
    return list_horario_options(db, turma_id=turma_id, data=data, turno=turno)


@router.get("/lookup/users-diretor-imagem")
def lookup_users_diretor_imagem(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_CHEFE)),
):
    """
    Usuários com papel 'diretor_imagem' que ainda não estão vinculados a um
    cadastro de Diretor de Imagem — usado em /admin/cadastros para o vínculo.
    """
    ja_vinculados = {
        str(d.user_id) for d in db.query(DiretorImagem).filter(DiretorImagem.user_id.isnot(None)).all()
    }
    usuarios = (
        db.query(User)
        .filter(User.role == "diretor_imagem", User.is_active == True)  # noqa: E712
        .order_by(User.full_name)
        .all()
    )
    return [
        {"id": str(u.id), "nome": u.full_name, "email": u.email}
        for u in usuarios
        if str(u.id) not in ja_vinculados
    ]


@router.get("/lookup/checklist-items")
def lookup_checklist_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    items = (
        db.query(ImageDirectorChecklistItem)
        .filter(ImageDirectorChecklistItem.ativo == True)  # noqa: E712
        .order_by(ImageDirectorChecklistItem.ordem, ImageDirectorChecklistItem.nome)
        .all()
    )
    return [ChecklistItemResponse.model_validate(i) for i in items]


@router.get("/lookup/questions")
def lookup_questions(
    nivel: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    q = db.query(ImageDirectorCustomQuestion).filter(
        ImageDirectorCustomQuestion.ativa == True  # noqa: E712
    )
    if nivel:
        q = q.filter(ImageDirectorCustomQuestion.nivel == nivel)
    questions = q.order_by(ImageDirectorCustomQuestion.ordem).all()
    return [CustomQuestionResponse.model_validate(x) for x in questions]


@router.get("/lookup/contexto-estudio")
def lookup_contexto_estudio(
    data: date = Query(...),
    turno: str = Query(...),
    estudio: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    """
    v3.5 - Auto preenchimento da escala diária e dos links/chaves de transmissão
    ao selecionar Data + Turno + Estúdio no formulário do Diretor de Imagem.
    """
    from app.models.agenda_estudio import EscalaDiaEstudio, EscalaFixaEstudio, AgendamentoEstudio
    from app.models.infraestrutura import Estudio
    from app.models.turma import Turma
    from app.models.auxiliares import Grade

    # 1. Encontrar o estúdio
    est = db.query(Estudio).filter(
        (Estudio.nome == estudio) | (Estudio.nome.ilike(f"%{estudio.strip()}%"))
    ).first()
    if not est:
        # "Estúdio 04" x "ESTÚDIO 4": compara normalizado
        from app.services.idr_txt_parser import norm_estudio
        est = next((e for e in db.query(Estudio).all() if norm_estudio(e.nome) == norm_estudio(estudio)), None)
    estudio_id = est.id if est else None

    turno_norm = turno.strip().lower()
    if "manh" in turno_norm:
        turno_agenda = "manha"
    elif "tard" in turno_norm:
        turno_agenda = "tarde"
    elif "noit" in turno_norm:
        turno_agenda = "noite"
    else:
        turno_agenda = turno_norm

    diretor_id = None
    diretor_nome = None
    escala_dia = None

    if estudio_id:
        # 2. Escala do dia
        escala_dia = db.query(EscalaDiaEstudio).filter(
            EscalaDiaEstudio.data == data,
            EscalaDiaEstudio.turno == turno_agenda,
            EscalaDiaEstudio.estudio_id == estudio_id,
        ).first()
        if escala_dia and escala_dia.diretor_imagem_id:
            diretor_id = str(escala_dia.diretor_imagem_id)
            diretor_nome = escala_dia.diretor.nome if escala_dia.diretor else None
        else:
            dia_sem = data.weekday()
            escala_fixa = db.query(EscalaFixaEstudio).filter(
                EscalaFixaEstudio.dia_semana == dia_sem,
                EscalaFixaEstudio.turno == turno_agenda,
                EscalaFixaEstudio.estudio_id == estudio_id,
            ).first()
            if escala_fixa and escala_fixa.diretor_imagem_id:
                diretor_id = str(escala_fixa.diretor_imagem_id)
                diretor_nome = escala_fixa.diretor.nome if escala_fixa.diretor else None

    # 3. Agendamentos ou eventos do estúdio
    youtube_link = None
    chave_transmissao = None
    is_evento = False
    nome_evento = None
    departamento = None
    responsavel = None
    chamado = None
    horario_inicio = None
    horario_fim = None

    # Link e chave do dia informados pelo diretor-chefe para o estúdio no turno (valem para todas as aulas)
    if estudio_id and escala_dia:
        youtube_link = escala_dia.youtube_link
        chave_transmissao = escala_dia.chave_transmissao
    link_da_agenda = bool(youtube_link)
    chave_da_agenda = bool(chave_transmissao)

    if estudio_id:
        ag = db.query(AgendamentoEstudio).filter(
            AgendamentoEstudio.data == data,
            AgendamentoEstudio.estudio_id == estudio_id,
            AgendamentoEstudio.status == "AGENDADO",
        ).first()
        if ag:
            if ag.chave_transmissao and not chave_transmissao:
                chave_transmissao = ag.chave_transmissao
            if not youtube_link and ag.chamado_link and ("youtube" in ag.chamado_link.lower() or "youtu.be" in ag.chamado_link.lower()):
                youtube_link = ag.chamado_link
            if ag.tipo == "EVENTO":
                is_evento = True
                nome_evento = ag.nome_evento or ag.titulo
                departamento = ag.departamento
                responsavel = ag.responsavel_evento
                chamado = ag.chamado
                horario_inicio = ag.horario_inicio.strftime("%H:%M") if ag.horario_inicio else None
                horario_fim = ag.horario_fim.strftime("%H:%M") if ag.horario_fim else None

    # 4. Fallback em relatórios já finalizados/rascunhos no estúdio/turno
    if not youtube_link or not chave_transmissao:
        idr_existente = db.query(ImageDirectorReport).filter(
            ImageDirectorReport.data_relatorio == data,
            ImageDirectorReport.turno.ilike(f"%{turno.strip()}%"),
            ImageDirectorReport.estudio.ilike(f"%{estudio.strip()}%"),
            ImageDirectorReport.is_deleted == False,
        ).first()
        if idr_existente:
            if not youtube_link and idr_existente.youtube_link:
                youtube_link = idr_existente.youtube_link
            if not chave_transmissao and idr_existente.chave_transmissao:
                chave_transmissao = idr_existente.chave_transmissao

    # 5. Dados de grade da turma vinculada ao estúdio
    turma_id = None
    turma_nome = None
    disciplina_id = None
    disciplina_nome = None
    professor_id = None
    professor_nome = None
    horario_aula = None

    if estudio_id and not is_evento:
        dia_sem = data.weekday()
        grade_slot = db.query(Grade).join(Turma, Grade.turma_id == Turma.id).filter(
            Grade.estudio_id == estudio_id,
            Grade.dia_semana == dia_sem,
            Turma.is_active == True,
        ).first()
        if grade_slot:
            turma_id = str(grade_slot.turma_id)
            turma_nome = grade_slot.turma.nome if grade_slot.turma else None
            disciplina_id = str(grade_slot.disciplina_id) if grade_slot.disciplina_id else None
            disciplina_nome = grade_slot.disciplina.nome if grade_slot.disciplina else None
            professor_id = str(grade_slot.professor_id) if grade_slot.professor_id else None
            professor_nome = grade_slot.professor.nome if grade_slot.professor else None
            if grade_slot.horario_inicio and grade_slot.horario_fim:
                horario_aula = f"{grade_slot.horario_inicio:%H:%M} às {grade_slot.horario_fim:%H:%M}"

    # Chave: só o diretor escalado no estúdio/turno (ou quem edita a Agenda)
    if current_user.role == "diretor_imagem":
        from app.models.diretor_imagem import DiretorImagem as _DI
        proprio = db.query(_DI).filter(_DI.user_id == current_user.id).first()
        escalados = {str(x) for x in (getattr(escala_dia, "diretor_imagem_id", None),
                                       getattr(escala_dia, "diretor2_imagem_id", None), diretor_id) if x}
        if escala_dia is not None and hasattr(escala_dia, "trocas"):
            escalados |= {t["diretor_imagem_id"] for t in escala_dia.trocas()}
        if not proprio or str(proprio.id) not in escalados:
            chave_transmissao = None

    return {
        "diretor_imagem_id": diretor_id,
        "diretor_nome": diretor_nome,
        "youtube_link": youtube_link,
        "chave_transmissao": chave_transmissao,
        # True = informado pelo diretor-chefe para o estúdio/turno do dia (fica travado no formulário)
        "link_da_agenda": link_da_agenda,
        "chave_da_agenda": chave_da_agenda,
        "is_evento": is_evento,
        "nome_evento": nome_evento,
        "departamento": departamento,
        "responsavel": responsavel,
        "chamado": chamado,
        "horario_inicio": horario_inicio,
        "horario_fim": horario_fim,
        "turma_id": turma_id,
        "turma_nome": turma_nome,
        "disciplina_id": disciplina_id,
        "disciplina_nome": disciplina_nome,
        "professor_id": professor_id,
        "professor_nome": professor_nome,
        "horario_aula": horario_aula,
    }


# ─── CRUD do Relatório ──────────────────────────────────────────────────

def _aplicar_transmissao_da_agenda(db: Session, report: ImageDirectorReport) -> None:
    """
    Link do YouTube e chave do estúdio no turno vêm do diretor-chefe (Agenda > Link e chave do dia).
    Quando informados, valem no relatório e o diretor só copia; não dá para trocar.
    """
    from app.services.agenda_estudios import transmissao_do_estudio
    tx = transmissao_do_estudio(db, report.data_relatorio, report.turno, report.estudio)
    if tx.get("youtube_link"):
        report.youtube_link = tx["youtube_link"]
    if tx.get("chave_transmissao"):
        report.chave_transmissao = tx["chave_transmissao"]


def _aplicar_aula_da_agenda(db: Session, report: ImageDirectorReport) -> None:
    """
    Aula marcada pelo diretor-chefe na Agenda (gravação antecipada, reposição…): o relatório
    herda quem solicitou, a data de referência e o chamado, sem o diretor precisar digitar.
    """
    if not report.turma_id or not report.data_relatorio or not report.start_time:
        return
    from datetime import date as _date
    from app.services.agenda_estudios import estudio_da_aula
    try:
        r = estudio_da_aula(db, report.turma_id, report.data_relatorio, inicio=report.start_time)
    except Exception:
        return
    if not r.get("encontrado"):
        return
    ex = r.get("exibicao_antecipada")
    if ex:
        # Exibição de aula gravada antes: aponta para a gravação (o pedido SEDUC vem da Agenda)
        from app.services.image_director_associacao import gerar_indicativo_exibicao
        report.solicitante_antecipacao = ex.get("solicitante") or report.solicitante_antecipacao
        report.motivo_referencia = gerar_indicativo_exibicao(_date.fromisoformat(ex["data_gravacao"]))
        if ex.get("chamado") and not (report.ticket_number or "").strip():
            report.ticket_number = ex["chamado"]
        return
    if not r.get("tipo_agenda"):
        return
    # Quem diz se é pedido da SEDUC é o diretor-chefe, na Agenda
    if r.get("solicitante_antecipacao"):
        report.solicitante_antecipacao = r["solicitante_antecipacao"]
    if r.get("data_referencia") and not report.data_referencia:
        report.data_referencia = _date.fromisoformat(r["data_referencia"])
        if not report.motivo_referencia:
            report.motivo_referencia = gerar_indicativo_reposicao(report.data_referencia)
    if r.get("chamado") and not (report.ticket_number or "").strip():
        report.ticket_number = r["chamado"]


@router.post("/", response_model=ImageDirectorReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ImageDirectorReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    diretor_id = _resolve_diretor_imagem_id(db, current_user, payload.diretor_imagem_id)

    existing = find_existing_report_by_slot(
        db,
        diretor_id,
        payload.data_relatorio,
        payload.turno,
        payload.estudio,
        class_report_id=payload.class_report_id,
        turma_id=payload.turma_id,
        horario_aula=payload.horario_aula,
        turno_variants=_turno_filter_variants(payload.turno),
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe relatório para este slot (id={existing.id}, status={existing.status}).",
        )

    report = ImageDirectorReport(
        created_by=current_user.id,
        diretor_imagem_id=diretor_id,
        data_relatorio=payload.data_relatorio,
        turno=payload.turno,
        estudio=payload.estudio,
        turma_id=payload.turma_id,
        serie_modulo_manual=payload.serie_modulo_manual,
        disciplina_id=payload.disciplina_id,
        disciplina_nome=payload.disciplina_nome,
        professor_id=payload.professor_id,
        professor_nome_externo=payload.professor_nome_externo,
        horario_aula=payload.horario_aula,
        regular=payload.regular or "Sim",
        ticket_number=payload.ticket_number,
        start_time=payload.start_time,
        end_time=payload.end_time,
        horario_entrada=payload.horario_entrada or datetime.now(timezone.utc).time(),
        horario_saida=payload.horario_saida,
        youtube_link=payload.youtube_link,
        chave_transmissao=payload.chave_transmissao,
        nome_evento=payload.nome_evento,
        departamento_solicitante=payload.departamento_solicitante,
        responsavel_evento=payload.responsavel_evento,
        solicitante_antecipacao=payload.solicitante_antecipacao,
        data_referencia=payload.data_referencia,
        motivo_referencia=payload.motivo_referencia or (gerar_indicativo_reposicao(payload.data_referencia) if payload.data_referencia else None),
        observacoes_gerais=payload.observacoes_gerais,
        origem=payload.origem or "grade",
        class_report_id=payload.class_report_id,
    )

    _aplicar_transmissao_da_agenda(db, report)
    db.add(report)
    db.flush()
    _apply_slot_times_from_horario(db, report)
    _aplicar_aula_da_agenda(db, report)

    associar_class_report(db, report, payload.class_report_id)
    db.commit()
    db.refresh(report)
    return _get_report_or_404(db, report.id)


def _class_report_audit_fields(cr: Optional[ClassReport]) -> dict:
    """Campos do ClassReport vinculado para a listagem de auditoria."""
    if not cr:
        return {}
    return {
        "class_report_status": cr.status,
        "class_report_status_compliance": cr.status_compliance or "Pendente",
        "class_report_nome_ficheiro_gerado": cr.nome_ficheiro_gerado,
        "class_report_video_link": cr.video_link,
        "class_report_slide_link": cr.slide_link,
        "class_report_creator_name": cr.creator_name,
        "class_report_validado_por_nome": cr.validado_por_nome,
        "class_report_precisa_correcao": cr.precisa_correcao,
    }


def build_idr_list_items(db: Session, reports: list) -> list:
    """Itens resumidos (histórico/auditoria) com horário exato, vínculo e grade."""

    report_ids = [r.id for r in reports]
    counts: dict = {}
    lesson_class_report_ids: dict = {}
    if report_ids:
        counts = dict(
            db.query(ImageDirectorLesson.report_id, func.count(ImageDirectorLesson.id))
            .filter(ImageDirectorLesson.report_id.in_(report_ids))
            .group_by(ImageDirectorLesson.report_id)
            .all()
        )

        # Relatórios "legado" (1 por turno) só guardam o vínculo com o ClassReport
        # de cada disciplina dentro de cada ImageDirectorLesson — sem isso, a Grade
        # Horária não consegue casar o status do Diretor com disciplinas que não
        # usam o fluxo "por slot" (ex.: disciplinas regulares/não-técnicas).
        for report_id, class_report_id in (
            db.query(ImageDirectorLesson.report_id, ImageDirectorLesson.class_report_id)
            .filter(
                ImageDirectorLesson.report_id.in_(report_ids),
                ImageDirectorLesson.class_report_id.isnot(None),
            )
            .all()
        ):
            lesson_class_report_ids.setdefault(report_id, []).append(class_report_id)

    cr_ids = [r.class_report_id for r in reports if r.class_report_id]
    cr_map: dict = {}
    if cr_ids:
        linked = (
            db.query(ClassReport)
            .options(joinedload(ClassReport.creator), joinedload(ClassReport.validador))
            .filter(ClassReport.id.in_(cr_ids), ClassReport.is_deleted == False)  # noqa: E712
            .all()
        )
        cr_map = {cr.id: cr for cr in linked}

    slot_cache: dict = {}
    display_times = {r.id: _slot_times_for_display(db, r, slot_cache) for r in reports}
    pertence_grade = {
        r.id: bool(lesson_class_report_ids.get(r.id)) or report_pertence_grade(db, r, slot_cache)
        for r in reports
    }
    ordinais = {
        r.id: resolve_slot_ordinal(
            db,
            turma_id=r.turma_id,
            data=r.data_relatorio,
            turno=r.turno,
            horario_aula=r.horario_aula,
            start_time=display_times[r.id][0],
            cache=slot_cache,
        )
        if (r.regular or "Sim") == "Sim"
        else None
        for r in reports
    }
    turma_ti: dict = {}
    for r in reports:
        if r.turma_id and r.turma_id not in turma_ti:
            turma_obj = r.turma or db.query(Turma).filter(Turma.id == r.turma_id).first()
            turma_ti[r.turma_id] = bool(turma_obj and _is_ti_turma(turma_obj))

    items = [
        ImageDirectorReportListItem(
            id=r.id,
            status=r.status,
            precisa_correcao=r.precisa_correcao,
            diretor_imagem_id=r.diretor_imagem_id,
            diretor_imagem_nome=r.diretor_imagem_nome,
            data_relatorio=r.data_relatorio,
            turno=r.turno,
            estudio=r.estudio,
            turma_id=r.turma_id,
            turma_nome=r.turma_nome,
            aulas_count=counts.get(r.id, 0),
            origem=getattr(r, "origem", "grade") or "grade",
            disciplina_id=r.disciplina_id,
            disciplina_nome=r.disciplina_nome,
            professor_nome=(r.professor_nome if r.professor_nome != "—" else None),
            horario_aula=r.horario_aula,
            start_time=display_times[r.id][0],
            end_time=display_times[r.id][1],
            horario_faixa=format_faixa(*display_times[r.id]),
            horario_ordinal=ordinais[r.id],
            regular=r.regular or "Sim",
            pertence_grade=pertence_grade[r.id],
            turma_ti=turma_ti.get(r.turma_id, False),
            class_report_id=r.class_report_id,
            lesson_class_report_ids=lesson_class_report_ids.get(r.id, []),
            youtube_link=r.youtube_link,
            validado_por_nome=r.validado_por_nome,
            **_class_report_audit_fields(cr_map.get(r.class_report_id)),
        )
        for r in reports
    ]
    return items


def _filtrar_idr_professor(db: Session, q, professor_id: UUID):
    """Professor do cabeçalho, nome externo ou professor de alguma aula do relatório."""
    prof_ids, prof_nome = professor_equivalentes(db, professor_id)
    conds = [ImageDirectorReport.professor_id.in_(prof_ids)]
    if prof_nome:
        ext = valores_equivalentes(db, ImageDirectorReport.professor_nome_externo, prof_nome)
        if ext:
            conds.append(ImageDirectorReport.professor_nome_externo.in_(ext))
        nomes_aula = valores_equivalentes(db, ImageDirectorLesson.professor_nome, prof_nome)
        if nomes_aula:
            por_aula = db.query(ImageDirectorLesson.report_id).filter(ImageDirectorLesson.professor_nome.in_(nomes_aula))
            conds.append(ImageDirectorReport.id.in_(por_aula))
    return q.filter(or_(*conds))


def _filtrar_idr_disciplina(db: Session, q, disciplina_id: UUID):
    """Disciplina do cabeçalho (id ou nome) ou de alguma aula do relatório."""
    disc_ids, disc_nome = disciplina_equivalentes(db, disciplina_id)
    conds = [ImageDirectorReport.disciplina_id.in_(disc_ids)]
    if disc_nome:
        cab = valores_equivalentes(db, ImageDirectorReport.disciplina_nome, disc_nome)
        if cab:
            conds.append(ImageDirectorReport.disciplina_nome.in_(cab))
        nomes_aula = valores_equivalentes(db, ImageDirectorLesson.disciplina_nome, disc_nome)
        if nomes_aula:
            por_aula = db.query(ImageDirectorLesson.report_id).filter(ImageDirectorLesson.disciplina_nome.in_(nomes_aula))
            conds.append(ImageDirectorReport.id.in_(por_aula))
    return q.filter(or_(*conds))


@router.get("/", response_model=PaginatedImageDirectorReports)
def list_reports(
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    turma_id: Optional[UUID] = Query(None),
    diretor_imagem_id: Optional[UUID] = Query(None),
    estudio: Optional[str] = Query(None),
    turno: Optional[str] = Query(None),
    status_filtro: Optional[str] = Query(None, alias="status"),
    precisa_correcao: Optional[bool] = Query(None),
    origem: Optional[str] = Query(None),
    transmissao_ou_gravada: Optional[str] = Query(
        None,
        description="Filtrar relatórios com ao menos uma aula deste tipo: Transmissão | Aula gravada",
    ),
    created_by: Optional[UUID] = Query(None, description="Filtrar pelo usuário que criou o ClassReport vinculado"),
    professor_id: Optional[UUID] = Query(None),
    disciplina_id: Optional[UUID] = Query(None),
    sem_vinculo: bool = Query(False, description="Só relatórios sem relatório de aula (assistente) vinculado"),
    sort_by: str = Query("data_relatorio", description="data_relatorio | created_at | finalized_at"),
    sort_order: str = Query("desc", description="asc | desc"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    from app.services.filtros import validar_periodo

    validar_periodo(data_inicio, data_fim)
    q = db.query(ImageDirectorReport).filter(ImageDirectorReport.is_deleted == False)  # noqa: E712

    if current_user.role not in PAPEIS_DIRETOR_CHEFE:
        own = _get_own_diretor_imagem(db, current_user)
        if not own:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        q = q.filter(ImageDirectorReport.diretor_imagem_id == own.id)
    elif diretor_imagem_id:
        q = q.filter(ImageDirectorReport.diretor_imagem_id == diretor_imagem_id)

    if data_inicio:
        q = q.filter(ImageDirectorReport.data_relatorio >= data_inicio)
    if data_fim:
        q = q.filter(ImageDirectorReport.data_relatorio <= data_fim)
    if turma_id:
        q = q.filter(ImageDirectorReport.turma_id == turma_id)
    if estudio:
        q = q.filter(ImageDirectorReport.estudio.in_(estudio_variantes(db, ImageDirectorReport.estudio, estudio)))
    if professor_id:
        q = _filtrar_idr_professor(db, q, professor_id)
    if disciplina_id:
        q = _filtrar_idr_disciplina(db, q, disciplina_id)
    if sem_vinculo:
        linked = db.query(ImageDirectorLesson.report_id).filter(ImageDirectorLesson.class_report_id.isnot(None))
        q = q.filter(
            ImageDirectorReport.class_report_id.is_(None),
            ~ImageDirectorReport.id.in_(linked),
        )
    if turno:
        variants = _turno_filter_variants(turno)
        q = q.filter(ImageDirectorReport.turno.in_(variants))
    if status_filtro:
        q = q.filter(ImageDirectorReport.status == status_filtro.strip().upper())
    if precisa_correcao is not None:
        q = q.filter(ImageDirectorReport.precisa_correcao == precisa_correcao)
    if origem:
        q = q.filter(ImageDirectorReport.origem == origem)
    if transmissao_ou_gravada:
        tipos_aula_permitidos = ("Transmissão", "Aula gravada")
        if transmissao_ou_gravada not in tipos_aula_permitidos:
            raise HTTPException(
                status_code=422,
                detail="transmissao_ou_gravada deve ser 'Transmissão' ou 'Aula gravada'.",
            )
        subq = (
            db.query(ImageDirectorLesson.report_id)
            .filter(ImageDirectorLesson.transmissao_ou_gravada == transmissao_ou_gravada)
            .distinct()
        )
        q = q.filter(ImageDirectorReport.id.in_(subq))
    if created_by:
        q = q.join(
            ClassReport,
            ImageDirectorReport.class_report_id == ClassReport.id,
        ).filter(
            ClassReport.created_by == created_by,
            ClassReport.is_deleted == False,  # noqa: E712
        )

    total = q.count()

    sort_columns = {
        "data_relatorio": ImageDirectorReport.data_relatorio,
        "created_at": ImageDirectorReport.created_at,
        "finalized_at": ImageDirectorReport.finalized_at,
    }
    sort_column = sort_columns.get(sort_by, ImageDirectorReport.data_relatorio)
    if sort_order == "asc":
        q = q.order_by(
            sort_column.asc(),
            ImageDirectorReport.turno.asc(),
            ImageDirectorReport.estudio.asc(),
            ImageDirectorReport.horario_aula.asc(),
            ImageDirectorReport.created_at.desc(),
        )
    else:
        q = q.order_by(
            sort_column.desc(),
            ImageDirectorReport.turno.asc(),
            ImageDirectorReport.estudio.asc(),
            ImageDirectorReport.horario_aula.asc(),
            ImageDirectorReport.created_at.desc(),
        )

    reports = q.offset(offset).limit(limit).all()
    items = build_idr_list_items(db, reports)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ─── PDF (rotas literais antes de /{report_id} para evitar conflito de path) ─

FINALIZED_IMAGE_STATUSES = ("AGUARDANDO_VALIDACAO", "VALIDADO", "FINALIZADO")


def _pdf_report_load_options():
    return (
        joinedload(ImageDirectorReport.lessons).joinedload(
            ImageDirectorLesson.respostas_extras
        ).joinedload(ImageDirectorCustomAnswer.question),
        joinedload(ImageDirectorReport.checklist_respostas).joinedload(
            ImageDirectorChecklistResponse.item
        ),
        joinedload(ImageDirectorReport.respostas_extras).joinedload(
            ImageDirectorCustomAnswer.question
        ),
    )


def _sort_grade_reports_for_pdf(reports: list) -> list:
    return sorted(
        reports,
        key=lambda r: (
            r.lessons[0].numero_aula if r.lessons else 999,
            r.horario_aula or "",
        ),
    )


def _fetch_grade_reports_for_pdf(
    db: Session,
    diretor_id: UUID,
    data: date,
    estudio: str,
    *,
    turno: Optional[str] = None,
    turma_id: Optional[UUID] = None,
    dia_completo: bool = False,
) -> tuple[list, bool]:
    """Retorna relatórios da grade ordenados e flag dia_completo efetivo."""
    estudio_ref = norm_estudio(estudio)
    q = (
        db.query(ImageDirectorReport)
        .options(*_pdf_report_load_options())
        .filter(
            ImageDirectorReport.diretor_imagem_id == diretor_id,
            ImageDirectorReport.data_relatorio == data,
            ImageDirectorReport.origem == "grade",
            ImageDirectorReport.is_deleted == False,  # noqa: E712
        )
    )

    effective_dia_completo = dia_completo
    if dia_completo:
        if not turma_id:
            raise HTTPException(
                status_code=400,
                detail="Informe turma_id para gerar o PDF dia completo.",
            )
        turma = db.query(Turma).filter(Turma.id == turma_id).first()
        if not turma or not _is_ti_turma(turma):
            raise HTTPException(
                status_code=400,
                detail="PDF dia completo disponível apenas para turmas de Tempo Integral (TI).",
            )
        q = q.filter(ImageDirectorReport.turma_id == turma_id)
    else:
        if not turno:
            raise HTTPException(status_code=400, detail="Informe o turno.")
        turno_variants = _turno_filter_variants(turno) or [turno]
        q = q.filter(ImageDirectorReport.turno.in_(turno_variants))
        if turma_id:
            q = q.filter(ImageDirectorReport.turma_id == turma_id)

    candidates = q.all()
    all_grade = _sort_grade_reports_for_pdf(
        [r for r in candidates if norm_estudio(r.estudio) == estudio_ref]
    )
    return all_grade, effective_dia_completo


@router.get("/pdf-turno")
def download_turno_pdf(
    request: Request,
    data: date = Query(...),
    estudio: str = Query(...),
    turno: Optional[str] = Query(None),
    turma_id: Optional[UUID] = Query(None),
    dia_completo: bool = Query(False, description="TI: PDF com todas as aulas do dia (Manhã+Tarde)"),
    diretor_imagem_id: Optional[UUID] = Query(None),
    report_id: Optional[UUID] = Query(
        None,
        description="Relatório único (Nova Aula / Gravação / turno com 1 aula): gera o PDF no formato do turno só com ele.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    """PDF consolidado — por turno (REGULAR/TECNICO) ou dia completo (TI)."""
    if report_id:
        single = (
            db.query(ImageDirectorReport)
            .options(*_pdf_report_load_options())
            .filter(ImageDirectorReport.id == report_id, ImageDirectorReport.is_deleted == False)  # noqa: E712
            .first()
        )
        if not single:
            raise HTTPException(status_code=404, detail="Relatório não encontrado.")
        _assert_can_manage(db, current_user, single)
        if single.status not in FINALIZED_IMAGE_STATUSES:
            raise HTTPException(
                status_code=400,
                detail="Finalize o relatório para gerar o PDF do turno.",
            )
        _attach_display_times(db, [single])
        pdf_bytes = render_turno_pdf([single], request)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{_pdf_filename(single)}"'},
        )

    diretor_id = diretor_imagem_id
    if current_user.role not in PAPEIS_DIRETOR_CHEFE:
        own = _get_own_diretor_imagem(db, current_user)
        if not own:
            raise HTTPException(status_code=403, detail="Diretor não vinculado.")
        diretor_id = own.id
    elif not diretor_id:
        raise HTTPException(status_code=400, detail="Informe diretor_imagem_id.")

    all_grade, is_dia_completo = _fetch_grade_reports_for_pdf(
        db,
        diretor_id,
        data,
        estudio,
        turno=turno,
        turma_id=turma_id,
        dia_completo=dia_completo,
    )
    if not all_grade:
        detail = (
            "Nenhum relatório da grade encontrado para este dia."
            if is_dia_completo
            else "Nenhum relatório da grade encontrado para este turno."
        )
        raise HTTPException(status_code=404, detail=detail)

    finalized = [r for r in all_grade if r.status in FINALIZED_IMAGE_STATUSES]
    if not finalized:
        raise HTTPException(
            status_code=400,
            detail="Nenhum relatório finalizado disponível para gerar o PDF.",
        )

    _attach_display_times(db, finalized)
    pdf_bytes = render_turno_pdf(finalized, request, dia_completo=is_dia_completo)
    filename = _pdf_filename(finalized[0])

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{report_id}", response_model=ImageDirectorReportResponse)
def get_report(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    report = _get_report_or_404(db, report_id)
    _assert_can_manage(db, current_user, report)
    resp = ImageDirectorReportResponse.model_validate(report)
    if not (resp.start_time and resp.end_time):
        st, et = _slot_times_for_display(db, report)
        resp.start_time, resp.end_time = st, et
    if (report.regular or "Sim") == "Sim":
        resp.horario_ordinal = resolve_slot_ordinal(
            db,
            turma_id=report.turma_id,
            data=report.data_relatorio,
            turno=report.turno,
            horario_aula=report.horario_aula,
            start_time=resp.start_time,
        )
    return resp


@router.put("/{report_id}", response_model=ImageDirectorReportResponse)
def update_report(
    report_id: UUID,
    payload: ImageDirectorReportUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    report = _get_report_or_404(db, report_id)
    _assert_can_manage(db, current_user, report)
    status_anterior = report.status
    reaberto = _assert_can_modify(report, current_user)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(report, field, value)


    if report.data_referencia and not report.motivo_referencia:
        report.motivo_referencia = gerar_indicativo_reposicao(report.data_referencia)

    _aplicar_transmissao_da_agenda(db, report)
    _apply_slot_times_from_horario(db, report)
    _aplicar_aula_da_agenda(db, report)
    associar_class_report(db, report)
    _versionar_se_finalizado(db, report, current_user, reaberto, status_anterior)
    db.commit()
    db.refresh(report)
    # Relatório já finalizado e salvo de novo (ex.: desmarcou o vídeo corrompido): busca os links
    from app.services.busca_links import disparar_busca_apos_diretor
    disparar_busca_apos_diretor(db, report)
    return report


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_CHEFE)),
):
    report = _get_report_or_404(db, report_id)
    registrar_versao(db, TIPO_IMAGEM, report, "EXCLUIDO", current_user, status_anterior=report.status)
    report.is_deleted = True
    db.add(AuditLog(
        actor_id=current_user.id,
        action="IMAGE_REPORT_DELETED",
        details=f"{current_user.full_name} arquivou o relatório de imagem {report.id}",
    ))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{report_id}/finalize", response_model=ImageDirectorReportResponse)
def finalize_report(
    report_id: UUID,
    payload: ImageDirectorFinalizeRequest = Body(default_factory=ImageDirectorFinalizeRequest),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    report = _get_report_or_404(db, report_id)
    _assert_can_manage(db, current_user, report)
    _assert_can_modify(report, current_user if report.status != estados.VALIDADO else None)
    status_anterior = report.status
    novo_status = estados.destino("finalizar", report.status)

    if payload.youtube_link:
        report.youtube_link = payload.youtube_link
    _aplicar_transmissao_da_agenda(db, report)

    db.flush()

    lesson_count = (
        db.query(ImageDirectorLesson)
        .filter(ImageDirectorLesson.report_id == report.id)
        .count()
    )
    if lesson_count == 0:
        raise HTTPException(
            status_code=422, detail="Adicione ao menos uma aula antes de finalizar o relatório."
        )

    if not report.youtube_link or not str(report.youtube_link).strip():
        raise HTTPException(
            status_code=422,
            detail="Falta o link do YouTube. Ele vem do que o diretor-chefe cadastra na Agenda "
                   "(Link e chave do dia) para este estúdio e turno.",
        )


    if report.data_referencia and not report.motivo_referencia:
        report.motivo_referencia = gerar_indicativo_reposicao(report.data_referencia)

    # Demanda 1.1 e 138: Trava de consistência com o ClassReport correspondente
    cr_correspondente = None
    if report.class_report_id:
        cr_correspondente = (
            db.query(ClassReport)
            .filter(ClassReport.id == report.class_report_id, ClassReport.is_deleted == False)
            .first()
        )
    if not cr_correspondente:
        cr_correspondente = _match_por_grade(db, report) or _match_por_caracteristicas(db, report)
    validar_consistencia_faturamento(cr_correspondente, report)

    # v3.2 — mesma lógica do Relatório de Aula: finalizar envia para a fila de
    # validação do Diretor-Chefe (AGUARDANDO_VALIDACAO), não direto para um
    # status "fechado". Horário de saída é carimbado automaticamente aqui.
    report.status = novo_status
    report.finalized_at = datetime.now(timezone.utc)
    report.horario_saida = report.horario_saida or datetime.now(timezone.utc).time()
    report.precisa_correcao = False
    report.observacao_coordenacao = None
    associar_class_report(db, report)
    registrar_versao(db, TIPO_IMAGEM, report, "FINALIZADO", current_user, status_anterior=status_anterior)

    log = AuditLog(
        actor_id=current_user.id,
        action="IMAGE_REPORT_FINALIZED",
        details=f"{current_user.full_name} finalizou o relatório de imagem {report.id}",
    )
    db.add(log)
    db.commit()
    db.refresh(report)
    # Reunião (out/2026): a busca dos links (vídeo e PDF) começa quando o diretor finaliza,
    # desde que o vídeo não esteja marcado como corrompido
    from app.services.busca_links import disparar_busca_apos_diretor
    disparar_busca_apos_diretor(db, report)
    return report


@router.post("/{report_id}/cancel", response_model=ImageDirectorReportResponse)
def cancel_report(
    report_id: UUID,
    payload: Optional[dict] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    report = _get_report_or_404(db, report_id)
    _assert_can_manage(db, current_user, report)
    status_anterior = report.status
    novo_status = estados.destino("cancelar", report.status)
    # v4: validado só o diretor-chefe/gestão cancela
    if status_anterior == estados.VALIDADO and current_user.role not in PAPEIS_DIRETOR_CHEFE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este relatório já foi validado. Só o diretor-chefe pode cancelá-lo.",
        )
    justificativa = ((payload or {}).get("justificativa") or "").strip() or "Não informada"
    report.status = novo_status
    report.justificativa_cancelamento = justificativa
    report.cancelado_por = current_user.id
    report.cancelado_em = datetime.now(timezone.utc)
    registrar_versao(db, TIPO_IMAGEM, report, "CANCELADO", current_user,
                     status_anterior=status_anterior, motivo=justificativa)

    log = AuditLog(
        actor_id=current_user.id,
        action="IMAGE_REPORT_CANCELLED",
        details=f"{current_user.full_name} cancelou o relatório de imagem {report.id}: {justificativa}",
    )
    db.add(log)
    db.commit()
    db.refresh(report)
    return report


@router.get("/{report_id}/conferencia-par")
def conferencia_do_par(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    """O que não bate entre este relatório e o do assistente da mesma aula (aviso antes de validar)."""
    report = _get_report_or_404(db, report_id)
    cr = None
    if report.class_report_id:
        cr = db.query(ClassReport).filter(
            ClassReport.id == report.class_report_id, ClassReport.is_deleted == False  # noqa: E712
        ).first()
    return {
        "tem_par": bool(cr),
        "par_id": str(cr.id) if cr else None,
        "divergencias": divergencias_do_par(cr, report) if cr else [],
    }


@router.patch("/{report_id}/validar", response_model=ImageDirectorReportResponse)
def validar_relatorio(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_CHEFE)),
):
    """
    v3.2 — Validação pelo Diretor-Chefe: confere o relatório de imagem do
    turno e marca como VALIDADO. Mesma lógica do Relatório de Aula.
    """
    report = _get_report_or_404(db, report_id)

    status_anterior = report.status
    novo_status = estados.destino("validar", report.status)
    # Reunião (out/2026): com vídeo marcado como corrompido o botão de validar fica travado
    from app.services.busca_links import video_corrompido
    if video_corrompido(report):
        raise HTTPException(
            status_code=400,
            detail="Vídeo marcado como corrompido. O diretor de imagem precisa recuperar o vídeo, "
                   "desmarcar \"vídeo corrompido\" e salvar antes da validação.",
        )

    report.status = novo_status
    report.precisa_correcao = False
    report.observacao_coordenacao = None
    report.validado_por = current_user.id
    report.validado_em = datetime.now(timezone.utc)
    registrar_versao(db, TIPO_IMAGEM, report, "VALIDADO", current_user, status_anterior=status_anterior)

    log = AuditLog(
        actor_id=current_user.id,
        action="IMAGE_REPORT_VALIDATED",
        details=f"{current_user.full_name} validou o relatório de imagem {report.id}",
    )
    db.add(log)
    db.commit()
    db.refresh(report)
    return report


@router.patch("/{report_id}/solicitar-correcao", response_model=ImageDirectorReportResponse)
def solicitar_correcao_relatorio(
    report_id: UUID,
    payload: ImageDirectorSolicitarCorrecao,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_CHEFE)),
):
    """
    v3.2 — Devolve o relatório de imagem para o Diretor corrigir: volta para
    RASCUNHO com precisa_correcao=True e a observação do Diretor-Chefe anexada.
    """
    report = _get_report_or_404(db, report_id)

    status_anterior = report.status
    report.status = estados.destino("devolver", report.status)
    report.precisa_correcao = True
    report.observacao_coordenacao = payload.observacao_coordenacao
    report.validado_por = None
    report.validado_em = None
    registrar_versao(db, TIPO_IMAGEM, report, "DEVOLVIDO", current_user,
                     status_anterior=status_anterior, motivo=payload.observacao_coordenacao)

    log = AuditLog(
        actor_id=current_user.id,
        action="IMAGE_REPORT_CORRECTION_REQUESTED",
        details=(
            f"{current_user.full_name} solicitou correção do relatório de imagem {report.id}: "
            f"{payload.observacao_coordenacao}"
        ),
    )
    db.add(log)
    db.commit()
    db.refresh(report)
    return report


# ─── Aulas (blocos "AULA 0X") ────────────────────────────────────────────

@router.post(
    "/{report_id}/lessons", response_model=ImageDirectorLessonResponse, status_code=status.HTTP_201_CREATED
)
def add_lesson(
    report_id: UUID,
    payload: ImageDirectorLessonCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    report = _get_report_or_404(db, report_id)
    _assert_can_manage(db, current_user, report)
    _status_antes = report.status
    _reaberto = _assert_can_modify(report, current_user)

    proximo_numero = (
        db.query(ImageDirectorLesson)
        .filter(ImageDirectorLesson.report_id == report.id)
        .count()
        + 1
    )

    lesson_data = payload.model_dump(exclude={"numero_aula"})
    numero_aula = payload.numero_aula or proximo_numero

    lesson = ImageDirectorLesson(
        report_id=report.id, numero_aula=numero_aula, **lesson_data
    )
    db.add(lesson)
    _versionar_se_finalizado(db, report, current_user, _reaberto, _status_antes)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.put("/{report_id}/lessons/{lesson_id}", response_model=ImageDirectorLessonResponse)
def update_lesson(
    report_id: UUID,
    lesson_id: UUID,
    payload: ImageDirectorLessonCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    report = _get_report_or_404(db, report_id)
    _assert_can_manage(db, current_user, report)
    _status_antes = report.status
    _reaberto = _assert_can_modify(report, current_user)

    lesson = (
        db.query(ImageDirectorLesson)
        .filter(ImageDirectorLesson.id == lesson_id, ImageDirectorLesson.report_id == report.id)
        .first()
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Aula não encontrada neste relatório.")

    for field, value in payload.model_dump(exclude={"numero_aula"}).items():
        setattr(lesson, field, value)
    if payload.numero_aula is not None:
        lesson.numero_aula = payload.numero_aula

    _versionar_se_finalizado(db, report, current_user, _reaberto, _status_antes)
    db.commit()
    db.refresh(lesson)
    db.refresh(report)
    # Desmarcou "vídeo corrompido" e salvou: dá o start na busca do link
    from app.services.busca_links import disparar_busca_apos_diretor
    disparar_busca_apos_diretor(db, report)
    return lesson


@router.delete("/{report_id}/lessons/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lesson(
    report_id: UUID,
    lesson_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    report = _get_report_or_404(db, report_id)
    _assert_can_manage(db, current_user, report)
    _status_antes = report.status
    _reaberto = _assert_can_modify(report, current_user)

    lesson = (
        db.query(ImageDirectorLesson)
        .filter(ImageDirectorLesson.id == lesson_id, ImageDirectorLesson.report_id == report.id)
        .first()
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Aula não encontrada neste relatório.")

    db.delete(lesson)
    _versionar_se_finalizado(db, report, current_user, _reaberto, _status_antes)
    db.commit()

    # Renumera as aulas restantes para não deixar buracos (AULA 01, 02...)
    restantes = (
        db.query(ImageDirectorLesson)
        .filter(ImageDirectorLesson.report_id == report.id)
        .order_by(ImageDirectorLesson.numero_aula)
        .all()
    )
    for idx, l in enumerate(restantes, start=1):
        l.numero_aula = idx
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Checklist de fechamento de estúdio (respostas do relatório) ────────

@router.put("/{report_id}/checklist", response_model=List[ChecklistAnswerIn])
def set_checklist_answers(
    report_id: UUID,
    payload: List[ChecklistAnswerIn],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    report = _get_report_or_404(db, report_id)
    _assert_can_manage(db, current_user, report)
    _status_antes = report.status
    _reaberto = _assert_can_modify(report, current_user)

    db.query(ImageDirectorChecklistResponse).filter(
        ImageDirectorChecklistResponse.report_id == report.id
    ).delete()

    for entry in payload:
        db.add(
            ImageDirectorChecklistResponse(
                report_id=report.id, item_id=entry.item_id, resposta=entry.resposta
            )
        )
    _versionar_se_finalizado(db, report, current_user, _reaberto, _status_antes)
    db.commit()
    return payload


# ─── Respostas às perguntas extras ──────────────────────────────────────

@router.put("/{report_id}/answers", response_model=List[CustomAnswerResponse])
def set_custom_answers(
    report_id: UUID,
    payload: List[CustomAnswerIn],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    report = _get_report_or_404(db, report_id)
    _assert_can_manage(db, current_user, report)
    _status_antes = report.status
    _reaberto = _assert_can_modify(report, current_user)

    # Remove respostas antigas (do relatório e das aulas dele) e recria.
    lesson_ids = [l.id for l in report.lessons]
    delete_filters = [ImageDirectorCustomAnswer.report_id == report.id]
    if lesson_ids:
        delete_filters.append(ImageDirectorCustomAnswer.lesson_id.in_(lesson_ids))
    db.query(ImageDirectorCustomAnswer).filter(or_(*delete_filters)).delete(synchronize_session=False)

    created = []
    for entry in payload:
        question = (
            db.query(ImageDirectorCustomQuestion)
            .filter(ImageDirectorCustomQuestion.id == entry.question_id)
            .first()
        )
        if not question:
            continue
        answer = ImageDirectorCustomAnswer(
            question_id=entry.question_id,
            lesson_id=entry.lesson_id,
            report_id=None if entry.lesson_id else report.id,
            resposta_texto=entry.resposta_texto,
            resposta_bool=entry.resposta_bool,
        )
        db.add(answer)
        created.append(answer)

    _versionar_se_finalizado(db, report, current_user, _reaberto, _status_antes)
    db.commit()
    for a in created:
        db.refresh(a)
    return created


# ─── PDF individual ──────────────────────────────────────────────────────

@router.get("/{report_id}/pdf")
def download_report_pdf(
    report_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_IMAGEM)),
):
    report = _get_report_or_404(db, report_id)
    _assert_can_manage(db, current_user, report)

    _attach_display_times(db, [report])
    pdf_bytes = render_report_pdf(report, request)
    filename = _pdf_filename(report)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Administração (Diretor-Chefe): checklist e perguntas extras ────────

@router.get("/admin/checklist-items", response_model=List[ChecklistItemResponse])
def list_checklist_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_CHEFE)),
):
    items = db.query(ImageDirectorChecklistItem).order_by(ImageDirectorChecklistItem.ordem).all()
    return items


@router.post(
    "/admin/checklist-items", response_model=ChecklistItemResponse, status_code=status.HTTP_201_CREATED
)
def create_checklist_item(
    payload: ChecklistItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_CHEFE)),
):
    item = ImageDirectorChecklistItem(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/admin/checklist-items/{item_id}", response_model=ChecklistItemResponse)
def update_checklist_item(
    item_id: UUID,
    payload: ChecklistItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_CHEFE)),
):
    item = db.query(ImageDirectorChecklistItem).filter(ImageDirectorChecklistItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/admin/checklist-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_checklist_item(
    item_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_CHEFE)),
):
    item = db.query(ImageDirectorChecklistItem).filter(ImageDirectorChecklistItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    item.ativo = False  # soft delete — preserva histórico dos relatórios já gerados
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/questions", response_model=List[CustomQuestionResponse])
def list_custom_questions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_CHEFE)),
):
    questions = (
        db.query(ImageDirectorCustomQuestion).order_by(ImageDirectorCustomQuestion.ordem).all()
    )
    return questions


@router.post(
    "/admin/questions", response_model=CustomQuestionResponse, status_code=status.HTTP_201_CREATED
)
def create_custom_question(
    payload: CustomQuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_CHEFE)),
):
    question = ImageDirectorCustomQuestion(created_by=current_user.id, **payload.model_dump())
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.put("/admin/questions/{question_id}", response_model=CustomQuestionResponse)
def update_custom_question(
    question_id: UUID,
    payload: CustomQuestionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_CHEFE)),
):
    question = (
        db.query(ImageDirectorCustomQuestion)
        .filter(ImageDirectorCustomQuestion.id == question_id)
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(question, field, value)
    db.commit()
    db.refresh(question)
    return question


@router.delete("/admin/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_question(
    question_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_DIRETOR_CHEFE)),
):
    question = (
        db.query(ImageDirectorCustomQuestion)
        .filter(ImageDirectorCustomQuestion.id == question_id)
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada.")
    question.ativa = False  # soft delete — preserva histórico das respostas já dadas
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
