"""
Canal Educação v3.0 — Endpoints de Versionamento de Grade (v2).
GradeVersao CRUD, slots, ativação e verificação de choque global.
"""

from datetime import datetime, time as time_type
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_role
from app.core.database import get_db
from app.models.auxiliares import Grade, Disciplina
from app.models.infraestrutura import GradeVersao, Estudio, CanalIptvModel, SlotHorario
from app.models.turma import Turma
from app.models.user import User

router = APIRouter(prefix="/api/v1", tags=["Grade Versão"])

DIAS_LABEL = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


# ─── Schemas ──────────────────────────────────────────────────────────

class SlotCreateIn(BaseModel):
    slot_horario_id: Optional[int] = None
    dia_semana: int
    disciplina_id: Optional[UUID] = None
    estudio_id: Optional[int] = None
    canal_iptv_id: Optional[int] = None
    tipo_slot: str = "aula"
    horario_inicio: Optional[str] = None
    horario_fim: Optional[str] = None


class ChoqueCheckIn(BaseModel):
    dia_semana: int
    horario_inicio: str
    horario_fim: str
    estudio_id: Optional[int] = None
    canal_iptv_id: Optional[int] = None
    grade_versao_id_excluir: Optional[int] = None


# ─── Helpers ──────────────────────────────────────────────────────────

def _parse_time(t_str: str) -> time_type:
    try:
        h, m = t_str.split(":")
        return time_type(int(h), int(m))
    except Exception:
        raise ValueError(f"Horário inválido: '{t_str}'")


def _verificar_choque(
    db: Session,
    dia_semana: int,
    horario_inicio: time_type,
    horario_fim: time_type,
    estudio_id: Optional[int],
    canal_iptv_id: Optional[int],
    grade_versao_id_excluir: Optional[int] = None,
) -> Optional[dict]:
    """Retorna detalhes do primeiro slot conflitante global, ou None.
    Retorna None imediatamente se nenhum recurso (estudio/canal) for informado."""
    resource_conditions = []
    if estudio_id is not None:
        resource_conditions.append(Grade.estudio_id == estudio_id)
    if canal_iptv_id is not None:
        resource_conditions.append(Grade.canal_iptv_id == canal_iptv_id)

    if not resource_conditions:
        return None

    q = (
        db.query(Grade, GradeVersao, Turma, Disciplina)
        .join(GradeVersao, Grade.grade_versao_id == GradeVersao.id)
        .join(Turma, GradeVersao.turma_id == Turma.id)
        .outerjoin(Disciplina, Grade.disciplina_id == Disciplina.id)
        .filter(
            GradeVersao.is_active == True,
            Turma.is_active == True,
            Grade.dia_semana == dia_semana,
            Grade.horario_inicio < horario_fim,
            Grade.horario_fim > horario_inicio,
            or_(*resource_conditions),
        )
    )
    if grade_versao_id_excluir:
        q = q.filter(Grade.grade_versao_id != grade_versao_id_excluir)

    row = q.first()
    if not row:
        return None

    grade, versao, turma, disc = row
    estudio = db.query(Estudio).filter(Estudio.id == grade.estudio_id).first() if grade.estudio_id else None
    canal = db.query(CanalIptvModel).filter(CanalIptvModel.id == grade.canal_iptv_id).first() if grade.canal_iptv_id else None

    if grade.estudio_id == estudio_id and estudio:
        recurso = estudio.nome
    elif canal:
        recurso = canal.nome
    else:
        recurso = "N/A"

    return {
        "turma": turma.nomenclatura_padrao or turma.nome,
        "disciplina": disc.nome if disc else "N/A",
        "dia_semana": DIAS_LABEL[grade.dia_semana] if 0 <= grade.dia_semana <= 6 else str(grade.dia_semana),
        "horario": f"{grade.horario_inicio.strftime('%H:%M')} às {grade.horario_fim.strftime('%H:%M')}",
        "recurso_conflitante": recurso,
    }


def _slot_to_dict(db: Session, g: Grade) -> dict:
    disc = db.query(Disciplina).filter(Disciplina.id == g.disciplina_id).first()
    est = db.query(Estudio).filter(Estudio.id == g.estudio_id).first()
    canal = db.query(CanalIptvModel).filter(CanalIptvModel.id == g.canal_iptv_id).first()
    return {
        "id": str(g.id),
        "dia_semana": g.dia_semana,
        "dia_semana_label": DIAS_LABEL[g.dia_semana] if 0 <= g.dia_semana <= 6 else str(g.dia_semana),
        "horario_inicio": g.horario_inicio.strftime("%H:%M") if g.horario_inicio else None,
        "horario_fim": g.horario_fim.strftime("%H:%M") if g.horario_fim else None,
        "disciplina_id": str(g.disciplina_id) if g.disciplina_id else None,
        "disciplina_nome": disc.nome if disc else None,
        "estudio_id": g.estudio_id,
        "estudio_nome": est.nome if est else None,
        "canal_iptv_id": g.canal_iptv_id,
        "canal_nome": canal.nome if canal else None,
        "tipo_slot": g.tipo_slot,
    }


# ─── Endpoint de verificação de choque ───────────────────────────────

@router.post("/grade/verificar-choque")
def verificar_choque(
    data: ChoqueCheckIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        h_ini = _parse_time(data.horario_inicio)
        h_fim = _parse_time(data.horario_fim)
    except ValueError as e:
        raise HTTPException(422, str(e))

    conflito = _verificar_choque(
        db, data.dia_semana, h_ini, h_fim,
        data.estudio_id, data.canal_iptv_id,
        data.grade_versao_id_excluir,
    )
    if conflito:
        return {"conflito": True, "detalhes": conflito}
    return {"conflito": False}


# ─── Grade Versão: listar e criar ────────────────────────────────────

@router.get("/turmas/{turma_id}/grade-versao")
def listar_versoes(
    turma_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(404, "Turma não encontrada.")
    versoes = (
        db.query(GradeVersao)
        .filter(GradeVersao.turma_id == turma_id)
        .order_by(GradeVersao.data_criacao.desc())
        .all()
    )
    return [
        {
            "id": v.id,
            "is_active": v.is_active,
            "data_ativacao": v.data_ativacao.isoformat() if v.data_ativacao else None,
            "data_criacao": v.data_criacao.isoformat(),
            "slots": [_slot_to_dict(db, g) for g in v.slots],
        }
        for v in versoes
    ]


@router.post("/turmas/{turma_id}/grade-versao", status_code=201)
def criar_versao(
    turma_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(404, "Turma não encontrada.")
    versao = GradeVersao(turma_id=turma_id, is_active=False, criado_por=current_user.id)
    db.add(versao)
    db.commit()
    db.refresh(versao)
    return {
        "id": versao.id,
        "is_active": versao.is_active,
        "data_criacao": versao.data_criacao.isoformat(),
    }


# ─── Grade Versão: slots ──────────────────────────────────────────────

@router.get("/turmas/{turma_id}/grade-versao/{versao_id}/slots")
def listar_slots_versao(
    turma_id: UUID,
    versao_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    versao = db.query(GradeVersao).filter(
        GradeVersao.id == versao_id,
        GradeVersao.turma_id == turma_id,
    ).first()
    if not versao:
        raise HTTPException(404, "Versão não encontrada.")
    return [_slot_to_dict(db, g) for g in versao.slots]


@router.post("/turmas/{turma_id}/grade-versao/{versao_id}/slots", status_code=201)
def adicionar_slot(
    turma_id: UUID,
    versao_id: int,
    slot_in: SlotCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    versao = db.query(GradeVersao).filter(
        GradeVersao.id == versao_id,
        GradeVersao.turma_id == turma_id,
    ).first()
    if not versao:
        raise HTTPException(404, "Versão não encontrada.")

    if slot_in.slot_horario_id:
        slot_ref = db.query(SlotHorario).filter(SlotHorario.id == slot_in.slot_horario_id).first()
        if not slot_ref:
            raise HTTPException(422, "slot_horario_id inválido.")
        h_ini = slot_ref.horario_inicio
        h_fim = slot_ref.horario_fim
    elif slot_in.horario_inicio and slot_in.horario_fim:
        try:
            h_ini = _parse_time(slot_in.horario_inicio)
            h_fim = _parse_time(slot_in.horario_fim)
        except ValueError as e:
            raise HTTPException(422, str(e))
    else:
        raise HTTPException(422, "Informe slot_horario_id ou horario_inicio/horario_fim.")

    # Se a versão estiver ativa, realiza verificação de choque antes de permitir
    if versao.is_active:
        conflito = _verificar_choque(
            db, slot_in.dia_semana, h_ini, h_fim,
            slot_in.estudio_id, slot_in.canal_iptv_id,
            grade_versao_id_excluir=versao_id,
        )
        if conflito:
            raise HTTPException(
                status_code=409,
                detail=f"⚠️ Conflito de horário detectado! Recurso '{conflito['recurso_conflitante']}' já está sendo usado pela turma '{conflito['turma']}' ({conflito['dia_semana']} às {conflito['horario']})."
            )

    if slot_in.estudio_id is not None:
        estudio = db.query(Estudio).filter(
            Estudio.id == slot_in.estudio_id, Estudio.ativo == True
        ).first()
        if not estudio:
            raise HTTPException(422, "Estúdio inativo ou não encontrado.")
        if not estudio.funciona_24h:
            if not (estudio.horario_inicio <= h_ini and estudio.horario_fim >= h_fim):
                raise HTTPException(
                    422,
                    f"Estúdio '{estudio.nome}' não funciona nesse horário "
                    f"({estudio.horario_inicio.strftime('%H:%M')}–{estudio.horario_fim.strftime('%H:%M')}).",
                )

    novo_slot = Grade(
        turma_id=turma_id,
        grade_versao_id=versao_id,
        slot_horario_id=slot_in.slot_horario_id,
        disciplina_id=slot_in.disciplina_id,
        estudio_id=slot_in.estudio_id,
        canal_iptv_id=slot_in.canal_iptv_id,
        tipo_slot=slot_in.tipo_slot,
        dia_semana=slot_in.dia_semana,
        horario_inicio=h_ini,
        horario_fim=h_fim,
    )
    db.add(novo_slot)
    db.commit()
    db.refresh(novo_slot)
    return {"id": str(novo_slot.id), "msg": "Slot adicionado."}


@router.delete(
    "/turmas/{turma_id}/grade-versao/{versao_id}/slots/{slot_id}",
    status_code=204,
)
def remover_slot(
    turma_id: UUID,
    versao_id: int,
    slot_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    versao = db.query(GradeVersao).filter(
        GradeVersao.id == versao_id,
        GradeVersao.turma_id == turma_id,
    ).first()
    if not versao:
        raise HTTPException(404, "Versão não encontrada.")
    slot = db.query(Grade).filter(
        Grade.id == slot_id,
        Grade.grade_versao_id == versao_id,
    ).first()
    if not slot:
        raise HTTPException(404, "Slot não encontrado.")
    db.delete(slot)
    db.commit()


# ─── Grade Versão: ativar ─────────────────────────────────────────────

@router.patch("/turmas/{turma_id}/grade-versao/{versao_id}/ativar")
def ativar_versao(
    turma_id: UUID,
    versao_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    versao = db.query(GradeVersao).filter(
        GradeVersao.id == versao_id,
        GradeVersao.turma_id == turma_id,
    ).first()
    if not versao:
        raise HTTPException(404, "Versão não encontrada.")
    if versao.is_active:
        raise HTTPException(409, "Versão já está ativa.")
    if not versao.slots:
        raise HTTPException(422, "Não é possível ativar uma versão sem slots.")

    # Verifica conflito de todos os slots antes de ativar
    conflitos = []
    for slot in versao.slots:
        c = _verificar_choque(
            db, slot.dia_semana, slot.horario_inicio, slot.horario_fim,
            slot.estudio_id, slot.canal_iptv_id,
            versao_id,
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
            409,
            {"message": "Conflito de horário detectado. Resolva antes de ativar.", "conflitos": conflitos},
        )

    try:
        db.query(GradeVersao).filter(
            GradeVersao.turma_id == turma_id,
            GradeVersao.is_active == True,
        ).update({"is_active": False})
        versao.is_active = True
        versao.data_ativacao = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Falha ao ativar versão. Tente novamente.")

    return {"message": "Versão ativada com sucesso.", "id": versao.id}
