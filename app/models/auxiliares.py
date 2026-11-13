"""
Canal Educação v3.0 — Modelos Auxiliares / Fundação.
Tabelas base: Unit, Professor, Disciplina, Grade, ProfessorDisciplina (M:N).
"""

import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Time, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Unit(Base):
    __tablename__ = "units"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(255), nullable=False)

    turmas = relationship("Turma", back_populates="unit")


class ProfessorDisciplina(Base):
    """Tabela associativa M:N entre Professor e Disciplina."""

    __tablename__ = "professor_disciplinas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    professor_id = Column(
        UUID(as_uuid=True), ForeignKey("professores.id"), nullable=False
    )
    disciplina_id = Column(
        UUID(as_uuid=True), ForeignKey("disciplinas.id"), nullable=False
    )


class Professor(Base):
    __tablename__ = "professores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)

    disciplinas = relationship(
        "Disciplina",
        secondary="professor_disciplinas",
        back_populates="professores",
    )


class Disciplina(Base):
    __tablename__ = "disciplinas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(255), nullable=False)
    nomenclatura_padrao = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    professores = relationship(
        "Professor",
        secondary="professor_disciplinas",
        back_populates="disciplinas",
    )


class Grade(Base):
    __tablename__ = "grades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # --- Relacionamentos principais ---
    turma_id = Column(UUID(as_uuid=True), ForeignKey("turmas.id"), nullable=True)
    disciplina_id = Column(UUID(as_uuid=True), ForeignKey("disciplinas.id"), nullable=True)
    professor_id = Column(UUID(as_uuid=True), ForeignKey("professores.id"), nullable=True)

    # --- Novos FKs (Grade v2) ---
    grade_versao_id = Column(Integer, ForeignKey("grade_versao.id"), nullable=True)
    slot_horario_id = Column(Integer, ForeignKey("slot_horario.id"), nullable=True)
    estudio_id = Column(Integer, ForeignKey("estudio.id"), nullable=True)
    canal_iptv_id = Column(Integer, ForeignKey("canal_iptv.id"), nullable=True)
    tipo_slot = Column(String(20), nullable=False, default="aula")

    # --- Horários ---
    dia_semana = Column(Integer, nullable=False, default=0)  # 0=Segunda … 6=Domingo
    horario_inicio = Column(Time, nullable=False)
    horario_fim = Column(Time, nullable=False)
    turno_aula = Column(String(20), nullable=True)

    # --- Legado (mantidos para não quebrar código existente) ---
    canal_iptv = Column(Integer, nullable=True)
    descricao = Column(String(255), nullable=True)
    vigencia_inicio = Column(Date, nullable=True)
    vigencia_fim = Column(Date, nullable=True)
    versao = Column(String(50), nullable=True)

    # --- Relationships ---
    turma = relationship("Turma", backref="grades")
    disciplina = relationship("Disciplina", backref="grades")
    professor = relationship("Professor", backref="grades")
    grade_versao = relationship("GradeVersao", back_populates="slots")
    estudio = relationship("Estudio")
    canal_iptv_obj = relationship("CanalIptvModel")
    slot_horario = relationship("SlotHorario")
