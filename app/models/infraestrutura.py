"""
Canal Educação v3.0 — Modelos de Infraestrutura (Grade Horária v2).
Estudio, CanalIptvModel, SlotHorario, GradeVersao.
"""

from datetime import datetime
from sqlalchemy import (
    Boolean, Column, Integer, String, Time, TIMESTAMP, ForeignKey, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Estudio(Base):
    __tablename__ = "estudio"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False)
    horario_inicio = Column(Time, nullable=False)
    horario_fim = Column(Time, nullable=False)
    funciona_24h = Column(Boolean, nullable=False, default=False)
    ativo = Column(Boolean, nullable=False, default=True)
    data_criacao = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)


class CanalIptvModel(Base):
    __tablename__ = "canal_iptv"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False)
    numero = Column(Integer, nullable=False, unique=True)
    ativo = Column(Boolean, nullable=False, default=True)
    data_criacao = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)


class SlotHorario(Base):
    __tablename__ = "slot_horario"

    id = Column(Integer, primary_key=True, autoincrement=True)
    turno = Column(String(20), nullable=False)
    ordem = Column(Integer, nullable=False)
    horario_inicio = Column(Time, nullable=False)
    horario_fim = Column(Time, nullable=False)
    ativo = Column(Boolean, nullable=False, default=True)
    data_criacao = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("turno IN ('manha','tarde','noite','madrugada')", name="chk_turno"),
        CheckConstraint("horario_fim > horario_inicio", name="chk_horario"),
    )


class GradeVersao(Base):
    __tablename__ = "grade_versao"

    id = Column(Integer, primary_key=True, autoincrement=True)
    turma_id = Column(UUID(as_uuid=True), ForeignKey("turmas.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    data_ativacao = Column(TIMESTAMP, nullable=True)
    data_criacao = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    criado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    turma = relationship("Turma", backref="grade_versoes")
    slots = relationship("Grade", back_populates="grade_versao")
