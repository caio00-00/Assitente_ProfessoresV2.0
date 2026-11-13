"""
Canal Educação v3.0 — Rotas de Gestão de Turmas.
CRUD de turmas com suporte a rascunho automático, ativação via GradeVersao e clonagem.
"""

from datetime import datetime, date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_role

# Quem mexe na Grade Horária "por turma" (incluir/excluir horário). Assistente e diretores só veem.
PAPEIS_EDITA_GRADE = ("admin", "gestor", "coordenador")
from app.core.database import get_db
from app.models.infraestrutura import GradeVersao, Estudio, CanalIptvModel, SlotHorario
from app.models.turma import Turma
from app.models.user import User


router = APIRouter(prefix="/api/v1/turmas", tags=["Gestão de Turmas"])


# ─── Schemas ──────────────────────────────────────────────────────────


class TurmaCreate(BaseModel):
    unit_id: Optional[UUID] = None
    nome: str
    modalidade: str
    serie_modulo: str
    turno: str
    nomenclatura_padrao: Optional[str] = None


class ClonarTurmaIn(BaseModel):
    nome: str
    nomenclatura_padrao: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────────


def _build_turma_status_map(db: Session, turma_ids: list) -> dict:
    """Returns a map of turma_id -> status dict, using 2 bulk queries."""
    if not turma_ids:
        return {}

    all_versoes = (
        db.query(GradeVersao)
        .filter(GradeVersao.turma_id.in_(turma_ids))
        .order_by(GradeVersao.turma_id, GradeVersao.data_criacao)
        .all()
    )

    versoes_by_turma: dict = {}
    for v in all_versoes:
        key = str(v.turma_id)
        versoes_by_turma.setdefault(key, []).append(v)

    result = {}
    for tid in turma_ids:
        key = str(tid)
        versoes = versoes_by_turma.get(key, [])
        active_v = next((v for v in versoes if v.is_active), None)
        draft_v = next((v for v in reversed(versoes) if not v.is_active), None)

        versao_num = None
        if active_v:
            for i, v in enumerate(versoes):
                if v.id == active_v.id:
                    versao_num = i + 1
                    break

        result[key] = {
            "status": "ativa" if active_v else "rascunho",
            "versao_ativa_id": active_v.id if active_v else None,
            "versao_ativa_num": versao_num,
            "draft_versao_id": draft_v.id if draft_v else None,
            "num_versoes": len(versoes),
            "data_ativacao": active_v.data_ativacao.isoformat() if active_v and active_v.data_ativacao else None,
        }
    return result


def _turma_to_dict(t: Turma, status_info: dict) -> dict:
    return {
        "id": str(t.id),
        "nome": t.nome,
        "modalidade": t.modalidade,
        "serie_modulo": t.serie_modulo,
        "turno": t.turno,
        "nomenclatura_padrao": t.nomenclatura_padrao,
        "nome_pasta_drive": t.nome_pasta_drive,
        "unit_id": str(t.unit_id) if t.unit_id else None,
        "is_active": t.is_active,
        **status_info,
    }


# ─── Rotas ────────────────────────────────────────────────────────────


@router.post("/", status_code=status.HTTP_201_CREATED)
def criar_turma(
    turma: TurmaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor"))  # v4: antes qualquer usuário logado,
):
    """Cria uma nova turma em estado rascunho (draft GradeVersao criado automaticamente)."""
    turno_upper = turma.turno.strip().upper()
    modalidade_upper = turma.modalidade.strip().upper()
    serie_upper = turma.serie_modulo.strip().upper()
    nome_upper = turma.nome.strip().upper()

    turnos_validos = {"MANHÃ", "TARDE", "NOITE", "INTEGRAL"}
    if turno_upper not in turnos_validos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Turno inválido ('{turma.turno}'). Escolha entre: {', '.join(turnos_validos)}.",
        )

    if "GRAVAÇÃO" not in modalidade_upper and "GRAVAÇÃO" not in nome_upper:
        if any("EJA" in s for s in [serie_upper, modalidade_upper, nome_upper]):
            if turno_upper != "NOITE":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Regra de Negócio: Turmas de EJA devem ocorrer no turno NOITE.",
                )
        if any("INTEGRAL" in s for s in [serie_upper, nome_upper]):
            if turno_upper == "NOITE":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Regra de Negócio: Turmas Integrais ocorrem apenas MANHÃ ou TARDE.",
                )

    turma_existente = (
        db.query(Turma)
        .filter(
            Turma.nome == turma.nome,
            Turma.turno == turma.turno,
            Turma.modalidade == turma.modalidade,
        )
        .first()
    )
    if turma_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe turma '{turma.nome}' no turno '{turma.turno}' / modalidade '{turma.modalidade}'.",
        )

    nova_turma = Turma(
        unit_id=turma.unit_id,
        nome=turma.nome,
        modalidade=turma.modalidade,
        serie_modulo=turma.serie_modulo,
        turno=turno_upper,
        nomenclatura_padrao=turma.nomenclatura_padrao,
    )
    db.add(nova_turma)
    try:
        db.flush()

        # Auto-cria GradeVersao em rascunho para a nova turma
        draft_versao = GradeVersao(
            turma_id=nova_turma.id,
            is_active=False,
            criado_por=current_user.id,
        )
        db.add(draft_versao)
        db.commit()
        db.refresh(nova_turma)

        status_map = _build_turma_status_map(db, [nova_turma.id])
        return _turma_to_dict(nova_turma, status_map.get(str(nova_turma.id), {}))
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Colisão de dados ao gravar turma.",
        )


@router.get("/")
def listar_turmas(
    incluir_inativos: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Lista todas as turmas com status de grade (ativa/rascunho)."""
    query = db.query(Turma)
    if not incluir_inativos:
        query = query.filter(Turma.is_active == True)
    turmas = query.all()
    if not turmas:
        return []

    status_map = _build_turma_status_map(db, [t.id for t in turmas])
    return [_turma_to_dict(t, status_map.get(str(t.id), {})) for t in turmas]


@router.get("/{turma_id}")
def obter_turma(
    turma_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Obtém detalhes de uma turma com status de grade."""
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada.")
    status_map = _build_turma_status_map(db, [turma_id])
    return _turma_to_dict(turma, status_map.get(str(turma_id), {}))


@router.put("/{turma_id}")
def editar_turma(
    turma_id: UUID,
    turma_in: TurmaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor"))  # v4: antes qualquer usuário logado,
):
    """Edita os dados básicos de uma turma."""
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada.")

    turno_upper = turma_in.turno.strip().upper()
    turma_existente = (
        db.query(Turma)
        .filter(
            Turma.nome == turma_in.nome,
            Turma.turno == turno_upper,
            Turma.modalidade == turma_in.modalidade,
            Turma.id != turma_id,
        )
        .first()
    )
    if turma_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe turma '{turma_in.nome}' no turno '{turno_upper}' / modalidade '{turma_in.modalidade}'.",
        )

    turma.nome = turma_in.nome
    turma.modalidade = turma_in.modalidade
    turma.serie_modulo = turma_in.serie_modulo
    turma.turno = turno_upper
    turma.nomenclatura_padrao = turma_in.nomenclatura_padrao

    db.commit()
    db.refresh(turma)
    status_map = _build_turma_status_map(db, [turma_id])
    return _turma_to_dict(turma, status_map.get(str(turma_id), {}))


@router.patch("/{turma_id}/toggle-active")
def toggle_active_turma(
    turma_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor"))  # v4: antes qualquer usuário logado,
):
    """Ativa ou desativa (soft delete) uma turma. Ao reativar, valida conflitos de horário."""
    from app.api.rotas_grade_versao import _verificar_choque, DIAS_LABEL
    from app.models.auxiliares import Grade

    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada.")

    reativando = not turma.is_active
    if reativando:
        # Verifica conflitos dos slots da versão ativa (se houver) antes de reativar
        active_versao = db.query(GradeVersao).filter(
            GradeVersao.turma_id == turma_id,
            GradeVersao.is_active == True,
        ).first()
        if active_versao:
            slots = db.query(Grade).filter(Grade.grade_versao_id == active_versao.id).all()
            conflitos = []
            for slot in slots:
                c = _verificar_choque(
                    db, slot.dia_semana, slot.horario_inicio, slot.horario_fim,
                    slot.estudio_id, slot.canal_iptv_id,
                )
                if c:
                    dia_label = DIAS_LABEL[slot.dia_semana] if 0 <= slot.dia_semana <= 6 else str(slot.dia_semana)
                    conflitos.append({
                        **c,
                        "slot_dia": dia_label,
                        "slot_horario": f"{slot.horario_inicio.strftime('%H:%M')} às {slot.horario_fim.strftime('%H:%M')}",
                    })
            if conflitos:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Não é possível reativar: conflitos de horário detectados.",
                        "conflitos": conflitos,
                    },
                )

    turma.is_active = not turma.is_active
    db.commit()
    return {"message": f"Turma {'ativada' if turma.is_active else 'inativada'} com sucesso."}


@router.post("/{turma_id}/clonar", status_code=201)
def clonar_turma(
    turma_id: UUID,
    data: ClonarTurmaIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor"))  # v4: antes qualquer usuário logado,
):
    """
    Cria uma nova turma independente copiando a estrutura (slots) de uma turma existente.
    A nova turma nasce em rascunho (Versão 1 só após ativação).
    """
    from app.models.auxiliares import Grade

    source = db.query(Turma).filter(Turma.id == turma_id).first()
    if not source:
        raise HTTPException(404, "Turma origem não encontrada.")

    existing = (
        db.query(Turma)
        .filter(Turma.nome == data.nome, Turma.turno == source.turno, Turma.modalidade == source.modalidade)
        .first()
    )
    if existing:
        raise HTTPException(409, f"Já existe turma '{data.nome}' com o mesmo turno/modalidade.")

    # Versão a copiar: prefere ativa, fallback para mais recente
    source_versao = (
        db.query(GradeVersao)
        .filter(GradeVersao.turma_id == turma_id, GradeVersao.is_active == True)
        .first()
    ) or (
        db.query(GradeVersao)
        .filter(GradeVersao.turma_id == turma_id)
        .order_by(GradeVersao.data_criacao.desc())
        .first()
    )

    nova = Turma(
        unit_id=source.unit_id,
        nome=data.nome,
        modalidade=source.modalidade,
        serie_modulo=source.serie_modulo,
        turno=source.turno,
        nomenclatura_padrao=data.nomenclatura_padrao or source.nomenclatura_padrao,
    )
    db.add(nova)
    db.flush()

    nova_versao = GradeVersao(turma_id=nova.id, is_active=False, criado_por=current_user.id)
    db.add(nova_versao)
    db.flush()

    slots_copiados = 0
    if source_versao:
        slots_source = db.query(Grade).filter(Grade.grade_versao_id == source_versao.id).all()
        for slot in slots_source:
            novo_slot = Grade(
                turma_id=nova.id,
                grade_versao_id=nova_versao.id,
                disciplina_id=slot.disciplina_id,
                estudio_id=slot.estudio_id,
                canal_iptv_id=slot.canal_iptv_id,
                tipo_slot=slot.tipo_slot,
                dia_semana=slot.dia_semana,
                horario_inicio=slot.horario_inicio,
                horario_fim=slot.horario_fim,
            )
            db.add(novo_slot)
            slots_copiados += 1

    db.commit()
    db.refresh(nova)
    return {
        "id": str(nova.id),
        "nome": nova.nome,
        "message": f"Turma clonada com sucesso. {slots_copiados} slot(s) copiado(s).",
        "slots_copiados": slots_copiados,
    }


# ─── Grade (rota legada — usada pela grade.html) ──────────────────────


@router.get("/{turma_id}/grade", status_code=status.HTTP_200_OK)
def listar_grade_turma(
    turma_id: UUID,
    data_consulta: Optional[str] = None,
    canal_iptv: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Retorna a grade horária vigente para a data consultada (usado pela grade.html).
    Combina slots da GradeVersao ativa com relatórios do dia.
    """
    from sqlalchemy import or_, and_

    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada.")

    target_date = date.today()
    if data_consulta:
        try:
            target_date = datetime.strptime(data_consulta, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de data inválido. Use YYYY-MM-DD.")

    from app.models.auxiliares import Grade, Disciplina
    from app.models.class_report import ClassReport
    import re

    query = db.query(Grade).filter(Grade.turma_id == turma_id)
    query = query.filter(
        and_(
            or_(Grade.vigencia_inicio <= target_date, Grade.vigencia_inicio.is_(None)),
            or_(Grade.vigencia_fim >= target_date, Grade.vigencia_fim.is_(None)),
        )
    )

    if canal_iptv is not None:
        query = query.filter(Grade.canal_iptv == canal_iptv)

    grades_raw = query.order_by(Grade.dia_semana, Grade.horario_inicio).all()

    def _hm(t) -> int:
        return t.hour * 60 + t.minute if t else 0

    # Nenhum filtro de deduplicação: todos os slots cadastrados são retornados
    # (o filtro legado de comparação consecutiva por disciplina_id foi removido
    # pois impedia aulas geminadas legítimas de aparecerem no payload).
    grades = grades_raw

    reports = (
        db.query(ClassReport)
        .filter(
            ClassReport.turma_id == turma_id,
            ClassReport.data_aula == target_date,
            ClassReport.is_deleted == False,
        )
        .all()
    )

    def normalize_to_digits(s: str) -> str:
        if not s:
            return ""
        digits = re.sub(r"\D", "", s)
        if digits:
            return digits
        return s.strip().upper()

    print(f"--- INICIANDO MATCH PARA TURMA {turma_id} ---")
    
    # Executa a correspondência (match) de slots e relatórios em duas etapas (two-pass)
    # matched_slots ligará o índice do slot na lista 'grades' ao relatório correspondente
    matched_slots = {}
    unmatched_reports = list(reports)
    
    from app.api.rotas_report import TIPOS_ESPECIAIS

    # Passo 0: GRAVAÇÃO — match por disciplina + tipo especial (ignora horário)
    for idx_g, g in enumerate(grades):
        is_gravacao = (g.horario_inicio.strftime("%H:%M") == "00:00") if g.horario_inicio else False
        if not is_gravacao:
            continue
        disc_id_str = str(g.disciplina_id) if g.disciplina_id else "None"
        match_idx = None
        for idx_r, r in enumerate(unmatched_reports):
            r_disc_id_str = str(r.disciplina_id) if r.disciplina_id else "None"
            if disc_id_str == r_disc_id_str and r.tipo_aula in TIPOS_ESPECIAIS:
                match_idx = idx_r
                break
        if match_idx is not None:
            matched_slots[idx_g] = unmatched_reports.pop(match_idx)

    # Passo 1: Correspondência estrita de (disciplina_id, horário)
    for idx_g, g in enumerate(grades):
        if idx_g in matched_slots:
            continue
        is_gravacao = (g.horario_inicio.strftime("%H:%M") == "00:00") if g.horario_inicio else False
        if is_gravacao:
            horario_label = "GRAVAÇÃO"
        else:
            h_ini = g.horario_inicio.strftime("%H:%M") if g.horario_inicio else ""
            h_fim = g.horario_fim.strftime("%H:%M") if g.horario_fim else ""
            horario_label = f"{h_ini} às {h_fim}"
            
        norm_grade_h = normalize_to_digits(horario_label)
        disc_id_str = str(g.disciplina_id) if g.disciplina_id else "None"
        
        match_idx = None
        for idx_r, r in enumerate(unmatched_reports):
            if r.tipo_aula in TIPOS_ESPECIAIS:
                continue
            norm_r_h = normalize_to_digits(r.horario_aula)
            r_disc_id_str = str(r.disciplina_id) if r.disciplina_id else "None"
            if norm_grade_h == norm_r_h and disc_id_str == r_disc_id_str:
                match_idx = idx_r
                break
            if not is_gravacao and r.start_time and r.end_time:
                faixa = f"{r.start_time.strftime('%H:%M')} às {r.end_time.strftime('%H:%M')}"
                if horario_label == faixa and disc_id_str == r_disc_id_str:
                    match_idx = idx_r
                    break
                
        if match_idx is not None:
            matched_slots[idx_g] = unmatched_reports.pop(match_idx)

    # Passo 2: Correspondência difusa por horário (ignora disciplina_id para lidar com substituições)
    for idx_g, g in enumerate(grades):
        if idx_g in matched_slots:
            continue
            
        is_gravacao = (g.horario_inicio.strftime("%H:%M") == "00:00") if g.horario_inicio else False
        if is_gravacao:
            horario_label = "GRAVAÇÃO"
        else:
            h_ini = g.horario_inicio.strftime("%H:%M") if g.horario_inicio else ""
            h_fim = g.horario_fim.strftime("%H:%M") if g.horario_fim else ""
            horario_label = f"{h_ini} às {h_fim}"
            
        norm_grade_h = normalize_to_digits(horario_label)
        
        match_idx = None
        for idx_r, r in enumerate(unmatched_reports):
            norm_r_h = normalize_to_digits(r.horario_aula)
            if norm_grade_h == norm_r_h:
                match_idx = idx_r
                break
                
        if match_idx is not None:
            matched_slots[idx_g] = unmatched_reports.pop(match_idx)

    DIAS_MAP = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"}
    resultado = []
    for idx_g, g in enumerate(grades):
        is_gravacao = (g.horario_inicio.strftime("%H:%M") == "00:00") if g.horario_inicio else False
        if is_gravacao:
            horario_label = "GRAVAÇÃO"
        else:
            h_ini = g.horario_inicio.strftime("%H:%M") if g.horario_inicio else ""
            h_fim = g.horario_fim.strftime("%H:%M") if g.horario_fim else ""
            horario_label = f"{h_ini} às {h_fim}"

        disc_id_str = str(g.disciplina_id) if g.disciplina_id else "None"
        r = matched_slots.get(idx_g)
        report_id = str(r.id) if r else None
        report_status = r.status if r else None
        
        print(f"[GRADE SLOT] ID: {g.id} | Horário: {horario_label} | Match: {'SIM' if report_id else 'NÃO'} (Status: {report_status})")

        est = db.query(Estudio).filter(Estudio.id == g.estudio_id).first() if g.estudio_id else None

        resultado.append(
            {
                "id": str(g.id),
                "dia_semana": DIAS_MAP.get(g.dia_semana, str(g.dia_semana)),
                "horario_inicio": g.horario_inicio.strftime("%H:%M") if g.horario_inicio else None,
                "horario_fim": g.horario_fim.strftime("%H:%M") if g.horario_fim else None,
                "turno_aula": g.turno_aula,
                "canal_iptv": g.canal_iptv,
                "disciplina_id": disc_id_str,
                "disciplina_nome": g.disciplina.nome if g.disciplina else "N/A",
                "professor_id": str(g.professor_id) if getattr(g, "professor_id", None) else None,
                "professor_nome": getattr(g.professor, "nome", "N/A") if getattr(g, "professor_id", None) else "N/A",
                "estudio_id": g.estudio_id,
                "estudio_nome": est.nome if est else None,
                "is_gravacao": is_gravacao,
                "gravacao_grade": (getattr(g, "tipo_slot", None) or "aula") == "gravacao",
                "versao": g.versao,
                "report_id": report_id,
                "report_status": report_status,
            }
        )

    return resultado


class GradeCreate(BaseModel):
    disciplina_id: UUID
    dia_semana: int
    horario_inicio: str
    horario_fim: str
    estudio_id: int
    canal_iptv: Optional[int] = None


@router.post("/{turma_id}/grade", status_code=status.HTTP_201_CREATED)
def adicionar_grade_turma(
    turma_id: UUID,
    grade_in: GradeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_EDITA_GRADE)),
):
    """Adiciona manualmente um horário na grade legada da turma."""
    from app.models.auxiliares import Grade
    from app.models.infraestrutura import Estudio

    estudio = db.query(Estudio).filter(Estudio.id == grade_in.estudio_id, Estudio.ativo == True).first()  # noqa: E712
    if not estudio:
        raise HTTPException(status_code=400, detail="Estúdio inválido ou inativo.")

    try:
        h_ini = datetime.strptime(grade_in.horario_inicio, "%H:%M").time()
        h_fim = datetime.strptime(grade_in.horario_fim, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de hora inválido. Use HH:MM.")

    minutos = h_ini.hour * 60 + h_ini.minute
    turno = "MANHÃ" if minutos < 720 else "TARDE" if minutos < 1100 else "NOITE"

    nova_grade = Grade(
        turma_id=turma_id,
        disciplina_id=grade_in.disciplina_id,
        dia_semana=grade_in.dia_semana,
        horario_inicio=h_ini,
        horario_fim=h_fim,
        turno_aula=turno,
        estudio_id=grade_in.estudio_id,
        canal_iptv=grade_in.canal_iptv,
    )
    db.add(nova_grade)
    db.commit()
    return {"id": str(nova_grade.id), "msg": "Horário adicionado com sucesso"}


@router.delete("/grade/{grade_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_grade_turma(
    grade_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_EDITA_GRADE)),
):
    """Remove um slot da grade legada."""
    from app.models.auxiliares import Grade

    grade = db.query(Grade).filter(Grade.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Slot não encontrado.")
    db.delete(grade)
    db.commit()
    return None


@router.get("/grade-estudio/{estudio_id}")
def listar_grade_estudio_turmas_route(
    estudio_id: int,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    data_consulta: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Retorna todos os slots da grade vinculados a um Estúdio para a semana,
    integrados com a Agenda de Estúdios (eventos, cancelamentos, remanejamentos).
    """
    from datetime import timedelta
    from app.services.agenda_estudios import grade_semana_estudio

    # Assistente vê a grade só por turma (sem visão por estúdio)
    if getattr(current_user, "role", None) == "assistente":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A grade por estúdio não está disponível para o assistente.")

    if data_inicio and data_fim:
        dt_ini = data_inicio
        dt_fim = data_fim
    elif data_consulta:
        dt_ini = data_consulta - timedelta(days=data_consulta.weekday())
        dt_fim = dt_ini + timedelta(days=6)
    else:
        hoje = date.today()
        dt_ini = hoje - timedelta(days=hoje.weekday())
        dt_fim = dt_ini + timedelta(days=6)

    return grade_semana_estudio(db, estudio_id, dt_ini, dt_fim)

