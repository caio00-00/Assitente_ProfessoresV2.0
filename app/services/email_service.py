import logging
import re
import smtplib
from email.message import EmailMessage
from typing import Callable, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

try:
    from app.core.celery_app import celery_app
except ImportError:  # Celery opcional fora do container/worker
    celery_app = None


def _clean_smtp_credential(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace('"', "").replace("'", "")


def _smtp_credentials_configured() -> tuple[str, str]:
    smtp_user = _clean_smtp_credential(settings.SMTP_USER)
    smtp_pass = _clean_smtp_credential(settings.SMTP_PASSWORD)
    return smtp_user, smtp_pass


def _email_domain_allowed(email: str) -> bool:
    domain = email.split("@")[-1].lower() if "@" in email else ""
    if domain in {"test.com", "example.com"}:
        return False
    allowed = [d.lower() for d in (settings.ALLOWED_EMAIL_DOMAINS or [])]
    if allowed and domain not in allowed:
        return False
    return True


def _connect_smtp() -> smtplib.SMTP:
    port = int(settings.SMTP_PORT)
    if port == 465:
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, port, timeout=30)
        server.ehlo()
        return server

    server = smtplib.SMTP(settings.SMTP_HOST, port, timeout=30)
    server.ehlo()
    if settings.SMTP_USE_TLS and port in (587, 25):
        server.starttls()
        server.ehlo()
    return server


def _send_smtp_message(message: EmailMessage, recipient: str, context: str) -> None:
    smtp_user, smtp_pass = _smtp_credentials_configured()
    if not smtp_user or not smtp_pass:
        base_domain = settings.APP_DOMAIN.rstrip("/")
        logger.warning(
            "%s: SMTP não configurado. Destinatário=%s",
            context,
            recipient,
        )
        return

    if not _email_domain_allowed(recipient):
        logger.warning(
            "%s: domínio não permitido para %s (ALLOWED_EMAIL_DOMAINS=%s)",
            context,
            recipient,
            settings.ALLOWED_EMAIL_DOMAINS,
        )
        return

    try:
        with _connect_smtp() as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(message)
        logger.info("%s: email enviado com sucesso para %s", context, recipient)
    except Exception:
        logger.exception("%s: falha ao enviar email para %s", context, recipient)
        raise


def send_invite_email_sync(email: str, full_name: str, token: str) -> None:
    base_domain = settings.APP_DOMAIN.rstrip("/")
    confirm_url = f"{base_domain}/confirm?token={token}"

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
    message["To"] = email
    message["Subject"] = "Ative sua conta no Canal Educação"
    message.set_content(
        f"Olá {full_name},\n\n"
        f"Sua conta foi criada. Ative-a aqui: {confirm_url}\n\n"
        f"Equipa Canal Educação"
    )
    _send_smtp_message(message, email, "Convite")


def send_reset_email_sync(email: str, full_name: str, token: str) -> None:
    base_domain = settings.APP_DOMAIN.rstrip("/")
    reset_url = f"{base_domain}/reset-password?token={token}"

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
    message["To"] = email
    message["Subject"] = "Recuperação de Senha — Canal Educação"
    message.set_content(
        f"Olá {full_name},\n\n"
        f"Recebemos uma solicitação para redefinir a sua senha.\n"
        f"Clique no link abaixo para criar uma nova senha:\n\n"
        f"{reset_url}\n\n"
        f"Este link é válido por 1 hora.\n"
        f"Se você não solicitou esta alteração, ignore este email.\n\n"
        f"Equipa Canal Educação"
    )
    _send_smtp_message(message, email, "Recuperação de senha")


def dispatch_auth_email(
    background_tasks,
    celery_task: Callable,
    sync_fn: Callable,
    *args,
) -> None:
    """
    Dispara email transacional de auth.
    Preferência: BackgroundTasks (confiável sem worker Celery).
    Fallback: fila Celery, se disponível e broker acessível.
    """
    if background_tasks is not None:
        background_tasks.add_task(sync_fn, *args)
        return

    if celery_task is None or get_settings().modo_tarefas == "direto":
        # v4.1: sem worker (Vercel) não há fila; envia na hora
        sync_fn(*args)
        return

    try:
        celery_task.delay(*args)
    except Exception:
        logger.exception(
            "Celery indisponível para %s; tentando envio síncrono.",
            sync_fn.__name__,
        )
        sync_fn(*args)


if celery_app is not None:

    @celery_app.task(bind=True, max_retries=3)
    def send_invite_email_task(self, email: str, full_name: str, token: str):
        try:
            send_invite_email_sync(email, full_name, token)
        except Exception as exc:
            raise self.retry(exc=exc, countdown=5)

    @celery_app.task(bind=True, max_retries=3)
    def send_reset_email_task(self, email: str, full_name: str, token: str):
        try:
            send_reset_email_sync(email, full_name, token)
        except Exception as exc:
            raise self.retry(exc=exc, countdown=5)

else:

    def send_invite_email_task(*_args, **_kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery não está instalado neste ambiente.")

    def send_reset_email_task(*_args, **_kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery não está instalado neste ambiente.")


def get_email_config_status() -> dict:
    """Resumo seguro da configuração de email (sem expor credenciais)."""
    smtp_user, smtp_pass = _smtp_credentials_configured()
    return {
        "smtp_host": settings.SMTP_HOST,
        "smtp_port": settings.SMTP_PORT,
        "smtp_use_tls": settings.SMTP_USE_TLS,
        "smtp_user_configured": bool(smtp_user),
        "smtp_password_configured": bool(smtp_pass),
        "smtp_from": settings.SMTP_FROM_EMAIL,
        "app_domain": settings.APP_DOMAIN,
        "allowed_email_domains": settings.ALLOWED_EMAIL_DOMAINS,
        "redis_url": settings.REDIS_URL,
    }
