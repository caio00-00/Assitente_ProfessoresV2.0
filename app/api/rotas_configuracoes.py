"""
Canal Educação v3.0 — Rotas de Configuração de Infraestrutura (Grade v2).
CRUD para Estudio, CanalIptvModel, SlotHorario.
"""

from datetime import date, time as time_type
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_role
from app.core.database import get_db
from app.models.infraestrutura import Estudio, CanalIptvModel, SlotHorario
from app.models.user import User

router = APIRouter(prefix="/api/v1/configuracoes", tags=["Configurações de Infraestrutura"])

# ── Turnos válidos e faixas de horário ────────────────────────────────

TURNO_FAIXAS = {
    "manha":     (time_type(5, 0),  time_type(12, 0)),
    "tarde":     (time_type(12, 0), time_type(18, 0)),
    "noite":     (time_type(18, 0), time_type(23, 59)),
    "madrugada": (time_type(0, 0),  time_type(5, 0)),
}


def _parse_time(t_str: str) -> time_type:
    try:
        h, m = t_str.split(":")
        return time_type(int(h), int(m))
    except Exception:
        raise ValueError(f"Horário inválido: '{t_str}'. Use HH:MM.")


def _slot_turno_valido(turno: str, inicio: time_type) -> bool:
    faixa = TURNO_FAIXAS.get(turno)
    if not faixa:
        return False
    inicio_faixa, fim_faixa = faixa
    if turno == "madrugada":
        return inicio >= inicio_faixa or inicio < fim_faixa
    return inicio_faixa <= inicio < fim_faixa


# ── Schemas ───────────────────────────────────────────────────────────

class EstudioIn(BaseModel):
    nome: str
    horario_inicio: str
    horario_fim: str
    funciona_24h: bool = False


class CanalIn(BaseModel):
    nome: str
    numero: int


class SlotIn(BaseModel):
    turno: str
    ordem: int
    horario_inicio: str
    horario_fim: str


# ── Helpers ───────────────────────────────────────────────────────────

def _fmt_time(t) -> Optional[str]:
    return t.strftime("%H:%M") if t else None


def _estudio_out(e: Estudio) -> dict:
    return {
        "id": e.id, "nome": e.nome,
        "horario_inicio": _fmt_time(e.horario_inicio),
        "horario_fim": _fmt_time(e.horario_fim),
        "funciona_24h": e.funciona_24h, "ativo": e.ativo,
    }


def _slot_out(s: SlotHorario) -> dict:
    return {
        "id": s.id, "turno": s.turno, "ordem": s.ordem,
        "horario_inicio": _fmt_time(s.horario_inicio),
        "horario_fim": _fmt_time(s.horario_fim), "ativo": s.ativo,
    }


# ── Estúdios ──────────────────────────────────────────────────────────

@router.get("/estudios")
def listar_estudios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return [_estudio_out(e) for e in db.query(Estudio).filter(Estudio.ativo == True).order_by(Estudio.id).all()]


@router.post("/estudios", status_code=201)
def criar_estudio(
    data: EstudioIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    h_ini = _parse_time(data.horario_inicio)
    h_fim = _parse_time(data.horario_fim)
    e = Estudio(nome=data.nome, horario_inicio=h_ini, horario_fim=h_fim, funciona_24h=data.funciona_24h)
    db.add(e)
    db.commit()
    db.refresh(e)
    return _estudio_out(e)


@router.patch("/estudios/{id}")
def editar_estudio(
    id: int,
    data: EstudioIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    e = db.query(Estudio).filter(Estudio.id == id).first()
    if not e:
        raise HTTPException(404, "Estúdio não encontrado.")
    e.nome = data.nome
    e.horario_inicio = _parse_time(data.horario_inicio)
    e.horario_fim = _parse_time(data.horario_fim)
    e.funciona_24h = data.funciona_24h
    db.commit()
    db.refresh(e)
    return _estudio_out(e)


@router.delete("/estudios/{id}", status_code=204)
def desativar_estudio(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    e = db.query(Estudio).filter(Estudio.id == id).first()
    if not e:
        raise HTTPException(404, "Estúdio não encontrado.")
    e.ativo = False
    db.commit()


@router.get("/estudios/{id}/grade")
def listar_grade_estudio(
    id: int,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    data_consulta: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Retorna os slots de grade e agendamentos de um estúdio na semana."""
    from datetime import date, timedelta
    from app.services.agenda_estudios import grade_semana_estudio

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

    return grade_semana_estudio(db, id, dt_ini, dt_fim)



# ── Canais IPTV ───────────────────────────────────────────────────────

@router.get("/canais-iptv")
def listar_canais(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return db.query(CanalIptvModel).filter(CanalIptvModel.ativo == True).order_by(CanalIptvModel.numero).all()


@router.post("/canais-iptv", status_code=201)
def criar_canal(
    data: CanalIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    if db.query(CanalIptvModel).filter(CanalIptvModel.numero == data.numero).first():
        raise HTTPException(409, f"Canal número {data.numero} já existe.")
    c = CanalIptvModel(nome=data.nome, numero=data.numero)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.patch("/canais-iptv/{id}")
def editar_canal(
    id: int,
    data: CanalIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    c = db.query(CanalIptvModel).filter(CanalIptvModel.id == id).first()
    if not c:
        raise HTTPException(404, "Canal não encontrado.")
    conflito = db.query(CanalIptvModel).filter(
        CanalIptvModel.numero == data.numero, CanalIptvModel.id != id
    ).first()
    if conflito:
        raise HTTPException(409, f"Canal número {data.numero} já existe.")
    c.nome = data.nome
    c.numero = data.numero
    db.commit()
    db.refresh(c)
    return c


@router.delete("/canais-iptv/{id}", status_code=204)
def desativar_canal(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    c = db.query(CanalIptvModel).filter(CanalIptvModel.id == id).first()
    if not c:
        raise HTTPException(404, "Canal não encontrado.")
    c.ativo = False
    db.commit()


# ── Slots de Horário ──────────────────────────────────────────────────

@router.get("/slots-horario")
def listar_slots(
    turno: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    q = db.query(SlotHorario)
    if turno:
        q = q.filter(SlotHorario.turno == turno.lower())
    return [_slot_out(s) for s in q.order_by(SlotHorario.turno, SlotHorario.ordem).all()]


@router.post("/slots-horario", status_code=201)
def criar_slot(
    data: SlotIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    turno = data.turno.lower()
    if turno not in TURNO_FAIXAS:
        raise HTTPException(422, f"Turno inválido. Use: {list(TURNO_FAIXAS.keys())}")
    h_ini = _parse_time(data.horario_inicio)
    h_fim = _parse_time(data.horario_fim)
    if not _slot_turno_valido(turno, h_ini):
        raise HTTPException(
            422,
            f"horario_inicio '{data.horario_inicio}' não pertence ao turno '{turno}'.",
        )
    s = SlotHorario(turno=turno, ordem=data.ordem, horario_inicio=h_ini, horario_fim=h_fim)
    db.add(s)
    db.commit()
    db.refresh(s)
    return _slot_out(s)


@router.patch("/slots-horario/{id}")
def editar_slot(
    id: int,
    data: SlotIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    s = db.query(SlotHorario).filter(SlotHorario.id == id).first()
    if not s:
        raise HTTPException(404, "Slot não encontrado.")
    turno = data.turno.lower()
    h_ini = _parse_time(data.horario_inicio)
    h_fim = _parse_time(data.horario_fim)
    if not _slot_turno_valido(turno, h_ini):
        raise HTTPException(
            422,
            f"horario_inicio '{data.horario_inicio}' não pertence ao turno '{turno}'.",
        )
    s.turno = turno
    s.ordem = data.ordem
    s.horario_inicio = h_ini
    s.horario_fim = h_fim
    db.commit()
    db.refresh(s)
    return _slot_out(s)


@router.delete("/slots-horario/{id}", status_code=204)
def desativar_slot(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    s = db.query(SlotHorario).filter(SlotHorario.id == id).first()
    if not s:
        raise HTTPException(404, "Slot não encontrado.")
    s.ativo = False
    db.commit()
