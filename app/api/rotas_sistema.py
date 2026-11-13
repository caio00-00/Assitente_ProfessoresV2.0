"""
Canal Educação v4.1 — Rotas de sistema (saúde, varredura do Drive, migração).

Pensadas para rodar sem worker (Vercel), mas funcionam em qualquer lugar:

- GET  /api/v1/sistema/saude      → público; diz se a API e o banco respondem
- GET  /api/v1/sistema/varredura  → cron da Vercel (manda Authorization: Bearer CRON_SECRET)
- POST /api/v1/sistema/varredura  → o mesmo, para cron externo (cron-job.org, GitHub Actions)
- POST /api/v1/sistema/migrar     → cria/atualiza as tabelas (o que o entrypoint
                                    do Docker faz ao subir; na Vercel não há esse passo)

As rotas protegidas aceitam o CRON_SECRET no cabeçalho Authorization. Sem
CRON_SECRET configurado, elas ficam desligadas (403), para nunca ficarem abertas.
"""

import hmac
import os
import re

from typing import Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter(prefix="/api/v1/sistema", tags=["Sistema"])


def _exigir_segredo(authorization: str = Header(default="")) -> None:
    segredo = get_settings().CRON_SECRET
    if not segredo:
        raise HTTPException(status_code=403, detail="Defina CRON_SECRET nas variáveis de ambiente para usar esta rota.")
    recebido = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(recebido.encode(), segredo.encode()):
        raise HTTPException(status_code=401, detail="Segredo inválido.")


@router.get("/saude")
def saude(db: Session = Depends(get_db)):
    s = get_settings()
    try:
        db.execute(text("SELECT 1"))
        banco = "ok"
    except Exception:  # noqa: BLE001
        banco = "sem conexão"
    return {
        "api": "ok",
        "banco": banco,
        "versao": s.APP_VERSION,
        "plataforma": "vercel" if s.eh_vercel else "docker",
        "busca_no_drive": s.modo_tarefas,
        "tempo_real": s.tempo_real,
    }


def _rodar_varredura(db: Session):
    from app.services.tarefas import varrer

    return varrer(db)


@router.get("/varredura", dependencies=[Depends(_exigir_segredo)])
def varredura_cron(db: Session = Depends(get_db)):
    """A Vercel chama os crons com GET."""
    return _rodar_varredura(db)


@router.post("/varredura", dependencies=[Depends(_exigir_segredo)])
def varredura(db: Session = Depends(get_db)):
    return _rodar_varredura(db)


def _url_migracao() -> str:
    s = get_settings()
    if s.DATABASE_URL_MIGRACAO:
        return s.DATABASE_URL_MIGRACAO
    url = s.DATABASE_URL
    # Supabase: 6543 = pooler em modo transação (bom para a API); 5432 = modo
    # sessão (necessário para a trava da migração). Mesmo host, outra porta.
    if "pooler.supabase.com" in url:
        url = re.sub(r":6543/", ":5432/", url)
    return url


class PrimeiroAdmin(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+$")
    senha: str = Field(min_length=8)
    nome: str = "Administrador"


class PedidoMigracao(BaseModel):
    # Só é usado se o banco ainda não tiver nenhum usuário (primeira instalação)
    primeiro_admin: Optional[PrimeiroAdmin] = None


def _criar_primeiro_admin(dados: PrimeiroAdmin) -> str:
    from app.core.database import SessionLocal
    from app.core.security import get_password_hash
    from app.models.user import User

    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return "ignorado: o banco já tem usuários"
        db.add(User(email=dados.email.lower(), full_name=dados.nome, role="admin",
                    hashed_password=get_password_hash(dados.senha), email_confirmed=True))
        db.commit()
        return "criado"
    finally:
        db.close()


@router.post("/migrar", dependencies=[Depends(_exigir_segredo)])
def migrar(pedido: Optional[PedidoMigracao] = Body(default=None)):
    """Cria as tabelas num banco vazio ou aplica as migrações novas. Pode repetir.
    Na primeira instalação, mande também o primeiro administrador."""
    from scripts.db_bootstrap import preparar_banco

    anterior = os.environ.get("DATABASE_URL")
    try:
        resultado = preparar_banco(_url_migracao())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha ao preparar o banco: {type(e).__name__}") from e
    finally:
        # preparar_banco aponta DATABASE_URL para a URL da migração; devolve a original
        if anterior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = anterior
    if pedido and pedido.primeiro_admin:
        resultado["primeiro_admin"] = _criar_primeiro_admin(pedido.primeiro_admin)
    return {"ok": True, **resultado}
