"""
Canal Educação v3.0 — Rotas de Autenticação e IAM.
Login por email, convites, confirmação de conta, RBAC, audit logging.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_role
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    generate_invite_token,
    get_invite_expiration,
    get_password_hash,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.auth import (
    AuditLogResponse,
    ConfirmAccountRequest,
    ForgotPasswordRequest,
    InviteRequest,
    InviteResponse,
    ResetPasswordRequest,
    TokenResponse,
    UserListResponse,
    UserResponse,
    UserThemeUpdate,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Autenticação e IAM"])


# ─── Helpers ──────────────────────────────────────────────────────────


def _create_audit_log(
    db: Session,
    actor_id,
    action: str,
    target_user_id=None,
    details: str = None,
    ip_address: str = None,
):
    """Cria um registo inalterável no log de auditoria."""
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        target_user_id=target_user_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(log)


# ─── Login ────────────────────────────────────────────────────────────


def _checar_limite_login(db: Session, email: str) -> None:
    """v4: bloqueia o e-mail por alguns minutos depois de várias senhas erradas."""
    from datetime import timedelta

    from app.core.config import get_settings
    from app.models.historico import LoginAttempt

    cfg = get_settings()
    if cfg.LOGIN_MAX_ATTEMPTS <= 0 or not email:
        return
    desde = datetime.now(timezone.utc) - timedelta(minutes=cfg.LOGIN_WINDOW_MINUTES)
    try:
        ultimo_ok = (
            db.query(func.max(LoginAttempt.criado_em))
            .filter(LoginAttempt.email == email, LoginAttempt.sucesso == "S")
            .scalar()
        )
        if ultimo_ok is not None and ultimo_ok.tzinfo is None:
            ultimo_ok = ultimo_ok.replace(tzinfo=timezone.utc)
        inicio = max(desde, ultimo_ok) if ultimo_ok else desde
        falhas = (
            db.query(func.count(LoginAttempt.id))
            .filter(LoginAttempt.email == email, LoginAttempt.sucesso == "N", LoginAttempt.criado_em >= inicio)
            .scalar()
        )
    except Exception:  # tabela ainda não criada: não impede o login
        db.rollback()
        return
    if falhas >= cfg.LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Muitas tentativas com senha errada. Tente de novo em {cfg.LOGIN_WINDOW_MINUTES} minutos ou use 'Esqueci a senha'.",
        )


def _registrar_tentativa(db: Session, email: str, ip, sucesso: bool) -> None:
    from app.models.historico import LoginAttempt

    try:
        db.add(LoginAttempt(email=email[:255], ip=(ip or "")[:64], sucesso="S" if sucesso else "N"))
        db.commit()
    except Exception:
        db.rollback()


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Autentica o utilizador por email e senha.
    O campo 'username' do OAuth2 form recebe o email.
    """
    # v4: e-mail sem diferença de maiúsculas e limite de tentativas por e-mail
    email = (form_data.username or "").strip().lower()
    ip = request.client.host if request.client else None
    _checar_limite_login(db, email)

    user = db.query(User).filter(func.lower(User.email) == email).first()

    if not user or not user.hashed_password or not verify_password(form_data.password, user.hashed_password):
        _registrar_tentativa(db, email, ip, sucesso=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _registrar_tentativa(db, email, ip, sucesso=True)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta desativada. Contacte o administrador.",
        )

    if not user.email_confirmed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email não confirmado. Verifique a sua caixa de entrada.",
        )

    access_token = create_access_token(
        data={"sub": user.email, "role": user.role, "user_id": str(user.id)}
    )
    return TokenResponse(access_token=access_token)


# ─── Convites ─────────────────────────────────────────────────────────


@router.post("/invite", response_model=InviteResponse)
def invite_user(
    invite_data: InviteRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    """
    Cria um convite para um novo utilizador.
    Apenas Admin e Gestor podem convidar.
    Gera token de 24h para confirmação via email.
    """
    # 1. Verifica se o email já está registado
    existing = db.query(User).filter(User.email == invite_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O email '{invite_data.email}' já está registado no sistema.",
        )

    # 2. Restrição de segurança: assistente não pode criar admin
    if invite_data.role == "admin" and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem criar contas de administrador.",
        )

    # 3. Gera o token e cria o utilizador com senha nula
    token = generate_invite_token()
    new_user = User(
        email=invite_data.email,
        full_name=invite_data.full_name,
        role=invite_data.role,
        hashed_password=None,  # Será definida na confirmação
        email_confirmed=False,
        invite_token=token,
        invite_expires_at=get_invite_expiration(),
        invited_by=current_user.id,
    )

    db.add(new_user)
    db.flush()

    # 4. Envio de email em background (não depende do worker Celery)
    from app.services.email_service import (
        dispatch_auth_email,
        send_invite_email_sync,
        send_invite_email_task,
    )
    dispatch_auth_email(
        background_tasks,
        send_invite_email_task,
        send_invite_email_sync,
        new_user.email,
        new_user.full_name,
        token,
    )
    # 5. Audit log: regista o convite
    _create_audit_log(
        db,
        actor_id=current_user.id,
        action="USER_INVITED",
        target_user_id=new_user.id,
        details=f"Convidou {invite_data.email} com perfil '{invite_data.role}'",
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    db.refresh(new_user)

    return InviteResponse(
        message=f"Convite enviado para {invite_data.email}.",
        email=invite_data.email,
        invite_token=token,
    )


@router.post("/users/{user_id}/resend-invite")
def resend_invite(
    user_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    """
    Reenvia o email de ativação para utilizador com conta ainda não confirmada.
    Gera novo token e renova a validade (INVITE_TOKEN_EXPIRE_HOURS).
    """
    from uuid import UUID as UUID_type

    try:
        uid = UUID_type(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de utilizador inválido.")

    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado.")

    if user.email_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Esta conta já foi confirmada. Use reset de senha se necessário.",
        )

    token = generate_invite_token()
    user.invite_token = token
    user.invite_expires_at = get_invite_expiration()

    from app.services.email_service import (
        dispatch_auth_email,
        send_invite_email_sync,
        send_invite_email_task,
    )
    dispatch_auth_email(
        background_tasks,
        send_invite_email_task,
        send_invite_email_sync,
        user.email,
        user.full_name,
        token,
    )

    _create_audit_log(
        db,
        actor_id=current_user.id,
        action="USER_INVITE_RESENT",
        target_user_id=user.id,
        details=f"Reenviou convite de ativação para {user.email}",
        ip_address=request.client.host if request.client else None,
    )

    db.commit()

    return {"message": f"Novo convite de ativação enviado para {user.email}."}


# ─── Confirmação de Conta ────────────────────────────────────────────


@router.post("/confirm", response_model=UserResponse)
def confirm_account(
    confirm_data: ConfirmAccountRequest,
    db: Session = Depends(get_db),
):
    """
    Confirma a conta e define a senha inicial.
    O token é recebido via link no email com validade de 24h.
    """
    try:
        user = db.query(User).filter(User.invite_token == confirm_data.token).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token de convite inválido.",
            )

        if user.email_confirmed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta conta já foi confirmada.",
            )

        # Verifica expiração
        now = datetime.now(timezone.utc)
        if user.invite_expires_at:
            # Gante que é offset-aware
            expires_at = user.invite_expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="Token de convite expirado. Solicite um novo convite.",
                )

        # Confirma e define a senha
        user.hashed_password = get_password_hash(confirm_data.password)
        user.email_confirmed = True
        user.invite_token = None  # Invalida o token após uso
        user.invite_expires_at = None

        db.commit()
        db.refresh(user)

        return user
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao confirmar a conta. Tente de novo ou peça um novo convite."
        )


# ─── Recuperação de Senha ─────────────────────────────────────────────


@router.post("/forgot-password")
def forgot_password(
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Envia um email com link de recuperação de senha.
    Por segurança, sempre retorna sucesso mesmo se o email não existir.
    """
    user = db.query(User).filter(User.email == data.email).first()

    if user and user.email_confirmed and user.is_active:
        # Gera token de reset  (1 hora de validade)
        from datetime import timedelta
        token = generate_invite_token()
        user.reset_token = token
        user.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()

        from app.services.email_service import (
            dispatch_auth_email,
            send_reset_email_sync,
            send_reset_email_task,
        )
        dispatch_auth_email(
            background_tasks,
            send_reset_email_task,
            send_reset_email_sync,
            user.email,
            user.full_name,
            token,
        )

    # Sempre retorna sucesso (segurança: não revela se email existe)
    return {
        "message": "Se o email estiver registado, enviámos um link de recuperação."
    }


@router.post("/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Redefine a senha usando o token de recuperação.
    """
    user = db.query(User).filter(User.reset_token == data.token).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de recuperação inválido ou expirado.",
        )

    # Verifica expiração
    now = datetime.now(timezone.utc)
    if user.reset_token_expires_at:
        expires_at = user.reset_token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            # Limpa o token expirado
            user.reset_token = None
            user.reset_token_expires_at = None
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Token de recuperação expirado. Solicite um novo.",
            )

    # Redefine a senha
    user.hashed_password = get_password_hash(data.password)
    user.reset_token = None
    user.reset_token_expires_at = None
    db.commit()

    return {"message": "Senha redefinida com sucesso. Pode fazer login."}


# ─── Perfil ───────────────────────────────────────────────────────────


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_active_user)):
    """Retorna os dados do utilizador autenticado."""
    return current_user


@router.patch("/me/theme", response_model=UserResponse)
def update_theme(
    data: UserThemeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Atualiza a preferência de tema do utilizador."""
    current_user.theme_preference = data.theme_preference
    db.commit()
    db.refresh(current_user)
    return current_user


# ─── Gestão de Utilizadores (Admin) ──────────────────────────────────


@router.get("/users", response_model=UserListResponse)
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "gestor")),
):
    """Lista todos os utilizadores (apenas Admin/Gestor)."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return UserListResponse(users=users, total=len(users))


@router.patch("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """
    Desativa um utilizador (Soft Delete).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilizador não encontrado.",
        )

    if str(user.id) == str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível desativar a sua própria conta.",
        )

    user.is_active = False

    _create_audit_log(
        db,
        actor_id=current_user.id,
        action="USER_DEACTIVATED",
        target_user_id=user.id,
        details=f"Desativou a conta de {user.email}",
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    return {"message": f"Utilizador {user.email} desativado com sucesso."}


@router.patch("/users/{user_id}/activate")
def activate_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """
    Reativa um utilizador que foi desativado.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilizador não encontrado.",
        )

    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Utilizador já está ativo.",
        )

    user.is_active = True

    _create_audit_log(
        db,
        actor_id=current_user.id,
        action="USER_ACTIVATED",
        target_user_id=user.id,
        details=f"Reativou a conta de {user.email}",
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    return {"message": f"Utilizador {user.email} reativado com sucesso."}


@router.patch("/users/{user_id}/role")
def change_user_role(
    user_id: str,
    role: str = Query(..., description="Novo perfil: admin, gestor, coordenador, auditor, assistente, diretor_imagem, diretor_chefe"),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """
    Altera o perfil de um utilizador.
    """
    valid_roles = {
        "admin",
        "gestor",
        "coordenador",
        "auditor",
        "assistente",
        "diretor_imagem",  # v3.2
        "diretor_chefe",   # v3.2
    }
    if role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Perfil inválido. Opções: {', '.join(valid_roles)}",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilizador não encontrado.",
        )

    old_role = user.role
    user.role = role

    _create_audit_log(
        db,
        actor_id=current_user.id,
        action="USER_ROLE_CHANGED",
        target_user_id=user.id,
        details=f"Alterou perfil de {user.email}: '{old_role}' → '{role}'",
        ip_address=request.client.host if request and request.client else None,
    )

    db.commit()
    return {
        "message": f"Perfil de {user.email} alterado para '{role}'.",
        "old_role": old_role,
        "new_role": role,
    }


# ─── Log de Auditoria ────────────────────────────────────────────────


@router.get("/audit-logs", response_model=List[AuditLogResponse])
def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """
    Lista o log de auditoria de acessos.
    """
    query = db.query(AuditLog)

    if action:
        query = query.filter(AuditLog.action == action)

    logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    return logs

# ─── TASK 14: Admin Force Password Reset ─────────────────────────────


@router.post("/users/{user_id}/force-reset")
def admin_force_reset_password(
    user_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """
    Admin: Força o reset de senha de qualquer utilizador.
    Gera um token de reset e envia o email de recuperação.
    """
    from uuid import UUID as UUID_type
    try:
        uid = UUID_type(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de utilizador inválido.")

    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado.")

    # Gera token de reset (1 hora de validade)
    from datetime import timedelta
    token = generate_invite_token()
    user.reset_token = token
    user.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    db.commit()

    from app.services.email_service import (
        dispatch_auth_email,
        send_reset_email_sync,
        send_reset_email_task,
    )
    dispatch_auth_email(
        background_tasks,
        send_reset_email_task,
        send_reset_email_sync,
        user.email,
        user.full_name,
        token,
    )

    # Audit log
    _create_audit_log(
        db,
        actor_id=current_user.id,
        action="FORCE_RESET_PASSWORD",
        target_user_id=user.id,
        details=f"Admin {current_user.full_name} forçou reset de senha para {user.email}",
        ip_address=request.client.host if request.client else None,
    )
    db.commit()  # v4: antes o log era criado depois do commit e se perdia

    return {
        "message": f"Email de recuperação de senha enviado para {user.email}."
    }


# ─── Setup Inicial (Admin Bootstrap) ─────────────────────────────────


@router.post("/bootstrap", response_model=UserResponse)
def bootstrap_admin(db: Session = Depends(get_db)):
    """
    Cria o primeiro administrador do sistema.
    """
    existing_users = db.query(User).count()
    if existing_users > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap só pode ser executado num sistema sem utilizadores.",
        )

    admin = User(
        email="admin@canaleducacao.com",
        full_name="Administrador Sistema",
        role="admin",
        hashed_password=get_password_hash("admin123"),
        email_confirmed=True,
    )

    db.add(admin)
    db.commit()
    db.refresh(admin)

    return admin