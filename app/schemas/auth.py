"""
Canal Educação v3.0 — Schemas de Autenticação (DTOs Pydantic).
Login, Tokens, Convites, Confirmação, Audit Log.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class InviteRequest(BaseModel):
    email: EmailStr
    full_name: str
    role: str = "assistente"  # admin, gestor, coordenador, auditor, assistente, diretor_imagem, diretor_chefe

    @field_validator("role")
    @classmethod
    def _papel_valido(cls, v: str) -> str:
        # v4: antes aceitava qualquer texto e criava usuário com papel inexistente
        from app.domain.politicas import PAPEIS_VALIDOS, normalizar_papel

        papel = normalizar_papel(v)
        if papel not in PAPEIS_VALIDOS:
            raise ValueError(f"Perfil inválido. Opções: {', '.join(sorted(PAPEIS_VALIDOS))}")
        return papel


class InviteResponse(BaseModel):
    message: str
    email: str
    invite_token: str


class ConfirmAccountRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=8)  # v4: mínimo 8 (antes 6)


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    email_confirmed: bool
    created_at: Optional[datetime] = None
    theme_preference: str = "dark"

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int

class UserThemeUpdate(BaseModel):
    theme_preference: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=8)  # v4: mínimo 8 (antes 6)


class AuditLogResponse(BaseModel):
    """Response para log de auditoria (§5.4)."""
    id: UUID
    actor_id: UUID
    action: str
    target_user_id: Optional[UUID] = None
    details: Optional[str] = None
    created_at: datetime
    ip_address: Optional[str] = None

    class Config:
        from_attributes = True
