"""
Canal Educação v4 — Histórico de versões dos relatórios e tentativas de login.

ReportVersion guarda uma "foto" (snapshot) do relatório a cada evento que muda
o seu estado ou o seu conteúdo: criação, edição, finalização, validação,
devolução, reabertura, cancelamento e exclusão. É a base para responder "o que
estava validado quando a aula foi cobrada" — antes do v4 um relatório validado
podia ser alterado sem deixar rastro.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base

# JSONB no Postgres, JSON nos testes (SQLite)
JSONVariante = JSON().with_variant(JSONB(), "postgresql")


def _agora():
    return datetime.now(timezone.utc)


class ReportVersion(Base):
    __tablename__ = "report_versions"
    __table_args__ = (
        UniqueConstraint("tipo", "report_id", "versao", name="uq_report_versions_tipo_report_versao"),
        Index("ix_report_versions_report", "tipo", "report_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # "class_report" (assistente) ou "image_director_report" (diretor de imagem)
    tipo = Column(String(40), nullable=False)
    report_id = Column(UUID(as_uuid=True), nullable=False)
    versao = Column(Integer, nullable=False)
    # CRIADO, EDITADO, FINALIZADO, VALIDADO, DEVOLVIDO, REABERTO, CANCELADO, EXCLUIDO
    evento = Column(String(30), nullable=False)
    status_anterior = Column(String(30), nullable=True)
    status_novo = Column(String(30), nullable=True)
    # Campos que mudaram neste evento: {"campo": [antes, depois]}
    alteracoes = Column(JSONVariante, nullable=True)
    snapshot = Column(JSONVariante, nullable=False)
    motivo = Column(Text, nullable=True)
    alterado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    alterado_em = Column(DateTime(timezone=True), nullable=False, default=_agora)


class LoginAttempt(Base):
    """Tentativas de login (para limitar força bruta entre vários processos)."""

    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_email_quando", "email", "criado_em"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False)
    ip = Column(String(64), nullable=True)
    sucesso = Column(String(1), nullable=False, default="N")  # S / N
    criado_em = Column(DateTime(timezone=True), nullable=False, default=_agora)
