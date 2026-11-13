"""
Canal Educação v3.0 — Dependency Injection.
Funções reutilizáveis para autenticação e autorização em rotas.
"""

import secrets

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.config import get_settings
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Valida o JWT e retorna o utilizador autenticado."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas ou token expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_email: str = payload.get("sub")
    if user_email is None:
        raise credentials_exception

    user = db.query(User).filter(User.email == user_email).first()
    if user is None or not user.is_active:
        raise credentials_exception

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Garante que o utilizador está ativo e com email confirmado."""
    if not current_user.email_confirmed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email não confirmado. Verifique o seu email.",
        )
    return current_user


def require_role(*allowed_roles: str):
    """
    Factory de dependency: restringe acesso por role.
    Uso: Depends(require_role("admin", "gestor"))
    """

    def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Sem permissão. Roles permitidas: {', '.join(allowed_roles)}",
            )
        return current_user

    return role_checker


# Perfis v3.2 — acesso exclusivo ao Relatório do Diretor de Imagem (sem relatórios de aula).
PAPEIS_SEM_CLASS_REPORT = frozenset({"diretor_imagem", "diretor_chefe"})


def require_class_report_access(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Bloqueia diretor_imagem e diretor_chefe em rotas de relatórios de aula."""
    if current_user.role in PAPEIS_SEM_CLASS_REPORT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este perfil não tem acesso a relatórios de aula.",
        )
    return current_user


def require_class_report_write(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    v4 — escrita em relatórios de aula: além dos diretores, bloqueia o auditor
    (somente leitura). A checagem de dono fica em app/domain/politicas.py.
    """
    require_class_report_access(current_user)
    if (current_user.role or "").lower() == "auditor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="O perfil de auditoria é somente leitura.",
        )
    return current_user


def verify_external_token(
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> str:
    """
    Valida a chave estática M2M enviada no header X-API-Key.
    Utilizado pelos endpoints da API externa (/api/v1/external).
    """
    settings = get_settings()

    if not settings.EXTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chave externa não configurada no servidor.",
        )

    if not secrets.compare_digest(x_api_key, settings.EXTERNAL_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chave inválida ou não autorizada.",
        )

    return x_api_key
