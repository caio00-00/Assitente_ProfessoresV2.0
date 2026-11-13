"""
Canal Educação v5 — Rotas da Aula.

API (JSON)
- GET  /api/v1/aulas                lista do período, com filtros
- GET  /api/v1/aulas/resumo         contagem por status
- GET  /api/v1/aulas/agora          por estúdio: no ar e a próxima
- POST /api/v1/aulas/sincronizar    recalcula um período (coordenação / admin)
- GET  /api/v1/aulas/{id}           uma aula

Fragmentos (HTML para o htmx; mesmo login por Bearer)
- GET  /parciais/aulas              a lista agrupada por dia
- GET  /parciais/aulas/agora        os cartões do modo Agora
- GET  /parciais/aulas/{id}         o painel de uma aula

Páginas
- GET  /aulas                       a tela Aulas
- GET  /aulas/agora                 tela cheia para a TV (sem menu)
"""

import os
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_role
from app.core.config import get_settings
from app.core.database import get_db
from app.models import aula as A
from app.models.user import User
from app.modulos.aulas import servico

api = APIRouter(prefix="/api/v1/aulas", tags=["Aulas (v5)"])
parciais = APIRouter(prefix="/parciais/aulas", tags=["Aulas (v5) — fragmentos"], include_in_schema=False)
paginas = APIRouter(include_in_schema=False)

_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
templates = Jinja2Templates(directory=os.path.abspath(_dir))
templates.env.globals["tempo_real"] = get_settings().tempo_real

_DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro"]


def dia_extenso(valor) -> str:
    """'2026-11-13' → 'Sexta, 13 de novembro'."""
    d = date.fromisoformat(valor) if isinstance(valor, str) else valor
    return f"{_DIAS[d.weekday()]}, {d.day} de {_MESES[d.month - 1]}"


templates.env.filters["dia_extenso"] = dia_extenso

PAPEIS_FORM_AULA = {"admin", "gestor", "coordenador", "coordenadora", "assistente"}
PAPEIS_FORM_IMAGEM = {"admin", "gestor", "diretor_chefe", "diretor_imagem"}
PAPEIS_SINCRONIZAR = ("admin", "gestor", "coordenador", "coordenadora", "diretor_chefe")


def _periodo(inicio: Optional[date], fim: Optional[date]):
    hoje = date.today()
    inicio = inicio or hoje
    fim = fim or inicio
    if fim < inicio:
        inicio, fim = fim, inicio
    if (fim - inicio).days > servico.MAX_DIAS:
        raise HTTPException(status_code=422, detail=f"Período máximo de {servico.MAX_DIAS} dias.")
    return inicio, fim


def _listar(db, user, inicio, fim, turma_id, estudio_id, status, q, minhas):
    inicio, fim = _periodo(inicio, fim)
    autor = user.id if (minhas and user.role == "assistente") else None
    aulas = servico.listar(db, inicio, fim, turma_id=turma_id, estudio_id=estudio_id, status=status,
                           busca=q, autor_id=autor)
    return inicio, fim, aulas


# ─── API ─────────────────────────────────────────────────────────────

@api.get("")
def listar_aulas(
    inicio: Optional[date] = None, fim: Optional[date] = None,
    turma_id: Optional[UUID] = None, estudio_id: Optional[int] = None,
    status: Optional[str] = None, q: Optional[str] = None, minhas: bool = False,
    db: Session = Depends(get_db), user: User = Depends(get_current_active_user),
):
    inicio, fim, aulas = _listar(db, user, inicio, fim, turma_id, estudio_id, status, q, minhas)
    return {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "resumo": servico.resumo(aulas),
            "aulas": servico.para_dicts(db, aulas)}


@api.get("/resumo")
def resumo_aulas(
    inicio: Optional[date] = None, fim: Optional[date] = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_active_user),
):
    inicio, fim = _periodo(inicio, fim)
    return servico.resumo(servico.listar(db, inicio, fim))


@api.get("/agora")
def aulas_agora(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return {"estudios": servico.agora(db)}


@api.post("/sincronizar", dependencies=[Depends(require_role(*PAPEIS_SINCRONIZAR))])
def sincronizar(inicio: date, fim: date, forcar: bool = False, db: Session = Depends(get_db)):
    inicio, fim = _periodo(inicio, fim)
    return {"dias_recalculados": servico.sincronizar_periodo(db, inicio, fim, forcar=forcar)}


@api.get("/{aula_id}")
def ver_aula(aula_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    a = db.get(A.Aula, aula_id)
    if not a:
        raise HTTPException(status_code=404, detail="Aula não encontrada.")
    servico.sincronizar_periodo(db, a.data, a.data)
    a = db.get(A.Aula, aula_id)
    if not a:
        raise HTTPException(status_code=404, detail="Esta aula saiu da grade.")
    return servico.para_dicts(db, [a])[0]


# ─── Fragmentos para o htmx ──────────────────────────────────────────

def _ctx(request, user, **extra):
    papel = (user.role or "").lower()
    return {"request": request, "papel": papel, "pode_aula": papel in PAPEIS_FORM_AULA,
            "pode_imagem": papel in PAPEIS_FORM_IMAGEM, "hoje": date.today().isoformat(), **extra}


@parciais.get("", response_class=HTMLResponse)
def parcial_lista(
    request: Request,
    inicio: Optional[date] = None, fim: Optional[date] = None,
    turma_id: Optional[str] = None, estudio_id: Optional[str] = None,
    status: Optional[str] = None, q: Optional[str] = None, minhas: Optional[str] = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_active_user),
):
    # campos vazios do formulário chegam como "" — viram "sem filtro"
    tid = UUID(turma_id) if turma_id else None
    eid = int(estudio_id) if estudio_id else None
    inicio, fim, aulas = _listar(db, user, inicio, fim, tid, eid, status or None, q or None, bool(minhas))
    itens = servico.para_dicts(db, aulas)
    dias = {}
    for it in itens:
        dias.setdefault(it["data"], []).append(it)
    return templates.TemplateResponse("aulas/_lista.html", _ctx(
        request, user, dias=dias, resumo=servico.resumo(aulas), inicio=inicio, fim=fim,
        rotulos=servico.STATUS_ROTULO))


@parciais.get("/agora", response_class=HTMLResponse)
def parcial_agora(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    from datetime import datetime
    return templates.TemplateResponse("aulas/_agora.html", _ctx(
        request, user, estudios=servico.agora(db), momento=datetime.now().strftime("%H:%M"),
        rotulos=servico.STATUS_ROTULO))


@parciais.get("/{aula_id}", response_class=HTMLResponse)
def parcial_aula(aula_id: UUID, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_current_active_user)):
    a = db.get(A.Aula, aula_id)
    if not a:
        raise HTTPException(status_code=404, detail="Aula não encontrada.")
    return templates.TemplateResponse("aulas/_detalhe.html", _ctx(
        request, user, a=servico.para_dicts(db, [a])[0], rotulos=servico.STATUS_ROTULO))


# ─── Páginas ─────────────────────────────────────────────────────────

@paginas.get("/aulas", response_class=HTMLResponse)
def pagina_aulas(request: Request):
    return templates.TemplateResponse("aulas/aulas.html", {"request": request})


@paginas.get("/aulas/agora", response_class=HTMLResponse)
def pagina_agora(request: Request):
    return templates.TemplateResponse("aulas/agora_tv.html", {"request": request})
