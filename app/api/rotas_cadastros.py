"""
Canal Educação v3.0 — Rotas de Cadastros (TASK 15).
CRUD para Professores, Disciplinas e Diretores de Imagem.
Inclui Soft Delete (is_active toggle).
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_role
from app.core.database import get_db
from app.models.auxiliares import Disciplina, Professor, ProfessorDisciplina
from app.models.diretor_imagem import DiretorImagem
from app.models.user import User

router = APIRouter(prefix="/api/v1/cadastros", tags=["Cadastros"])


# ─── Schemas ──────────────────────────────────────────────────────────


class ProfessorCreate(BaseModel):
    nome: str
    disciplina_ids: Optional[List[UUID]] = None


class ProfessorUpdate(BaseModel):
    nome: Optional[str] = None
    disciplina_ids: Optional[List[UUID]] = None


class ProfessorOut(BaseModel):
    id: UUID
    nome: str
    is_active: bool
    disciplinas: List[dict] = []

    class Config:
        from_attributes = True


class DisciplinaCreate(BaseModel):
    nome: str
    nomenclatura_padrao: Optional[str] = None


class DisciplinaUpdate(BaseModel):
    nome: Optional[str] = None
    nomenclatura_padrao: Optional[str] = None


class DisciplinaOut(BaseModel):
    id: UUID
    nome: str
    nomenclatura_padrao: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class DiretorCreate(BaseModel):
    nome: str
    user_id: Optional[UUID] = None  # v3.2 — vincula a um usuário com login


class DiretorUpdate(BaseModel):
    nome: Optional[str] = None
    user_id: Optional[UUID] = None  # v3.2


class DiretorOut(BaseModel):
    id: UUID
    nome: str
    is_active: bool
    user_id: Optional[UUID] = None
    user_email: Optional[str] = None

    class Config:
        from_attributes = True


# ─── Professores ──────────────────────────────────────────────────────


@router.get("/professores", response_model=List[ProfessorOut])
def listar_professores(
    incluir_inativos: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Lista todos os professores. Admins/gestores podem ver inativos."""
    query = db.query(Professor)
    if not incluir_inativos:
        query = query.filter(Professor.is_active == True)
    profs = query.order_by(Professor.nome).all()

    result = []
    for p in profs:
        result.append({
            "id": p.id,
            "nome": p.nome,
            "is_active": p.is_active,
            "disciplinas": [{"id": d.id, "nome": d.nome} for d in p.disciplinas],
        })
    return result


@router.post("/professores", response_model=ProfessorOut, status_code=status.HTTP_201_CREATED)
def criar_professor(
    data: ProfessorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    """Cria um novo professor."""
    existing = db.query(Professor).filter(Professor.nome == data.nome).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Professor '{data.nome}' já existe.")

    prof = Professor(nome=data.nome)
    db.add(prof)
    db.flush()

    # Vincular disciplinas
    if data.disciplina_ids:
        for disc_id in data.disciplina_ids:
            link = ProfessorDisciplina(professor_id=prof.id, disciplina_id=disc_id)
            db.add(link)

    db.commit()
    db.refresh(prof)

    return {
        "id": prof.id,
        "nome": prof.nome,
        "is_active": prof.is_active,
        "disciplinas": [{"id": d.id, "nome": d.nome} for d in prof.disciplinas],
    }


@router.patch("/professores/{professor_id}")
def editar_professor(
    professor_id: UUID,
    data: ProfessorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    """Edita os dados de um professor."""
    prof = db.query(Professor).filter(Professor.id == professor_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Professor não encontrado.")

    if data.nome is not None:
        prof.nome = data.nome

    if data.disciplina_ids is not None:
        # Remove vínculos existentes e recria
        db.query(ProfessorDisciplina).filter(
            ProfessorDisciplina.professor_id == professor_id
        ).delete()
        for disc_id in data.disciplina_ids:
            link = ProfessorDisciplina(professor_id=prof.id, disciplina_id=disc_id)
            db.add(link)

    db.commit()
    db.refresh(prof)

    return {
        "id": prof.id,
        "nome": prof.nome,
        "is_active": prof.is_active,
        "disciplinas": [{"id": d.id, "nome": d.nome} for d in prof.disciplinas],
    }


@router.patch("/professores/{professor_id}/toggle-active")
def toggle_professor(
    professor_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    """Ativa/desativa um professor (Soft Delete)."""
    prof = db.query(Professor).filter(Professor.id == professor_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Professor não encontrado.")

    prof.is_active = not prof.is_active
    db.commit()

    status_text = "ativado" if prof.is_active else "desativado"
    return {"message": f"Professor '{prof.nome}' {status_text}.", "is_active": prof.is_active}


# ─── Disciplinas ──────────────────────────────────────────────────────


@router.get("/disciplinas", response_model=List[DisciplinaOut])
def listar_disciplinas_crud(
    incluir_inativos: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Lista todas as disciplinas."""
    query = db.query(Disciplina)
    if not incluir_inativos:
        query = query.filter(Disciplina.is_active == True)
    return query.order_by(Disciplina.nome).all()


@router.post("/disciplinas", response_model=DisciplinaOut, status_code=status.HTTP_201_CREATED)
def criar_disciplina(
    data: DisciplinaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    """Cria uma nova disciplina."""
    existing = db.query(Disciplina).filter(Disciplina.nome == data.nome).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Disciplina '{data.nome}' já existe.")

    disc = Disciplina(nome=data.nome, nomenclatura_padrao=data.nomenclatura_padrao)
    db.add(disc)
    db.commit()
    db.refresh(disc)
    return disc


@router.patch("/disciplinas/{disciplina_id}")
def editar_disciplina(
    disciplina_id: UUID,
    data: DisciplinaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    """Edita os dados de uma disciplina."""
    disc = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
    if not disc:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada.")

    if data.nome is not None:
        disc.nome = data.nome
    if data.nomenclatura_padrao is not None:
        disc.nomenclatura_padrao = data.nomenclatura_padrao

    db.commit()
    db.refresh(disc)
    return disc


@router.patch("/disciplinas/{disciplina_id}/toggle-active")
def toggle_disciplina(
    disciplina_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    """Ativa/desativa uma disciplina (Soft Delete)."""
    disc = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
    if not disc:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada.")

    disc.is_active = not disc.is_active
    db.commit()

    status_text = "ativada" if disc.is_active else "desativada"
    return {"message": f"Disciplina '{disc.nome}' {status_text}.", "is_active": disc.is_active}


# ─── Diretores de Imagem ─────────────────────────────────────────────


@router.get("/diretores", response_model=List[DiretorOut])
def listar_diretores_crud(
    incluir_inativos: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Lista todos os diretores de imagem."""
    query = db.query(DiretorImagem)
    if not incluir_inativos:
        query = query.filter(DiretorImagem.is_active == True)
    return query.order_by(DiretorImagem.nome).all()


@router.post("/diretores", response_model=DiretorOut, status_code=status.HTTP_201_CREATED)
def criar_diretor(
    data: DiretorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor", "diretor_chefe")),
):
    """Cria um novo diretor de imagem."""
    existing = db.query(DiretorImagem).filter(DiretorImagem.nome == data.nome).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Diretor '{data.nome}' já existe.")

    if data.user_id is not None:
        _validar_user_diretor(db, data.user_id)

    diretor = DiretorImagem(nome=data.nome, user_id=data.user_id)
    db.add(diretor)
    db.commit()
    db.refresh(diretor)
    return diretor


@router.patch("/diretores/{diretor_id}")
def editar_diretor(
    diretor_id: UUID,
    data: DiretorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor", "diretor_chefe")),
):
    """Edita os dados de um diretor de imagem."""
    diretor = db.query(DiretorImagem).filter(DiretorImagem.id == diretor_id).first()
    if not diretor:
        raise HTTPException(status_code=404, detail="Diretor não encontrado.")

    if data.nome is not None:
        diretor.nome = data.nome

    if data.user_id is not None:
        _validar_user_diretor(db, data.user_id, ignorar_diretor_id=diretor.id)
        diretor.user_id = data.user_id

    db.commit()
    db.refresh(diretor)
    return diretor


def _validar_user_diretor(db: Session, user_id: UUID, ignorar_diretor_id: Optional[UUID] = None):
    """
    Garante que o usuário existe, tem papel compatível e ainda não está
    vinculado a outro cadastro de Diretor de Imagem (vínculo é 1:1).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    q = db.query(DiretorImagem).filter(DiretorImagem.user_id == user_id)
    if ignorar_diretor_id:
        q = q.filter(DiretorImagem.id != ignorar_diretor_id)
    if q.first():
        raise HTTPException(
            status_code=409,
            detail=f"O usuário '{user.email}' já está vinculado a outro diretor de imagem.",
        )


@router.patch("/diretores/{diretor_id}/toggle-active")
def toggle_diretor(
    diretor_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor", "diretor_chefe")),
):
    """Ativa/desativa um diretor de imagem (Soft Delete)."""
    diretor = db.query(DiretorImagem).filter(DiretorImagem.id == diretor_id).first()
    if not diretor:
        raise HTTPException(status_code=404, detail="Diretor não encontrado.")

    diretor.is_active = not diretor.is_active
    db.commit()

    status_text = "ativado" if diretor.is_active else "desativado"
    return {"message": f"Diretor '{diretor.nome}' {status_text}.", "is_active": diretor.is_active}
