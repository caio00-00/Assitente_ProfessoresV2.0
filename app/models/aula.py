"""
Canal Educação v5 — A Aula.

Cada aula prevista vira um registro: a grade vigente do dia (com cancelamentos
e remanejamentos lançados na Agenda) e as gravações/aulas extras da Agenda.
Os dois relatórios (assistente e diretor de imagem) ficam ligados a ela.

As aulas são DERIVADAS: o serviço app/modulos/aulas/servico.py as recalcula a
partir da grade, da agenda e dos relatórios (sincronizar_dia). Os relatórios
continuam sendo a fonte dos dados; apagar uma aula nunca apaga relatório.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, Time,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

# Status calculado da aula (ordem = ordem do fluxo)
PREVISTA = "prevista"                  # ainda vai acontecer
SEM_RELATORIO = "sem_relatorio"        # já passou e ninguém fez o relatório
EM_RELATORIO = "em_relatorio"          # relatório de aula em rascunho
DEVOLVIDA = "devolvida"                # coordenação devolveu para correção
AGUARDANDO_VALIDACAO = "aguardando_validacao"
AGUARDANDO_IMAGEM = "aguardando_imagem"  # aula validada, falta o lado da imagem
VALIDADA = "validada"                  # os dois lados validados → faturável
CANCELADA = "cancelada"

STATUS_AULA = (PREVISTA, SEM_RELATORIO, EM_RELATORIO, DEVOLVIDA, AGUARDANDO_VALIDACAO,
               AGUARDANDO_IMAGEM, VALIDADA, CANCELADA)

# De onde a aula veio
ORIGEM_GRADE = "grade"          # slot da grade vigente
ORIGEM_AGENDA = "agenda"        # gravação / aula extra marcada na Agenda
ORIGEM_RELATORIO = "relatorio"  # relatório sem aula prevista correspondente


class Aula(Base):
    __tablename__ = "aulas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data = Column(Date, nullable=False, index=True)
    turma_id = Column(UUID(as_uuid=True), ForeignKey("turmas.id"), nullable=True, index=True)
    disciplina_id = Column(UUID(as_uuid=True), ForeignKey("disciplinas.id"), nullable=True)
    professor_id = Column(UUID(as_uuid=True), ForeignKey("professores.id"), nullable=True)
    estudio_id = Column(Integer, ForeignKey("estudio.id"), nullable=True, index=True)
    inicio = Column(Time, nullable=True)
    fim = Column(Time, nullable=True)
    horario_texto = Column(String(50), nullable=True)   # "1º Horário", "08:00 às 09:00"
    tipo = Column(String(30), nullable=False, default="aula")  # aula | gravacao | aula_extra
    origem = Column(String(20), nullable=False, default=ORIGEM_GRADE)

    # Ligações com a origem (uma aula da grade por dia; um agendamento por dia)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True)
    agendamento_id = Column(UUID(as_uuid=True), ForeignKey("agenda_agendamentos.id", ondelete="SET NULL"), nullable=True)
    remanejada = Column(Boolean, nullable=False, default=False)
    cancelada_na_agenda = Column(Boolean, nullable=False, default=False)
    motivo_cancelamento = Column(Text, nullable=True)
    fora_da_grade = Column(Boolean, nullable=False, default=False)  # saiu da grade depois do relatório

    # Os relatórios ligados
    class_report_id = Column(UUID(as_uuid=True), ForeignKey("class_reports.id", ondelete="SET NULL"), nullable=True, index=True)
    image_director_report_id = Column(UUID(as_uuid=True), ForeignKey("image_director_reports.id", ondelete="SET NULL"), nullable=True, index=True)
    image_director_lesson_id = Column(UUID(as_uuid=True), ForeignKey("image_director_lessons.id", ondelete="SET NULL"), nullable=True)

    # Calculados (para filtrar e contar sem recalcular)
    status = Column(String(30), nullable=False, default=PREVISTA, index=True)
    tem_video = Column(Boolean, nullable=False, default=False)
    tem_pdf = Column(Boolean, nullable=False, default=False)
    cobrar = Column(String(80), nullable=True)

    criado_em = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    atualizado_em = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ux_aulas_data_grade", "data", "grade_id", unique=True, postgresql_where=grade_id.isnot(None)),
        Index("ux_aulas_data_agendamento", "data", "agendamento_id", unique=True,
              postgresql_where=agendamento_id.isnot(None)),
        Index("ux_aulas_class_report", "class_report_id", unique=True, postgresql_where=class_report_id.isnot(None)),
        Index("ix_aulas_data_status", "data", "status"),
    )


class AulaSincronizacao(Base):
    """Quando cada dia foi recalculado e com que 'assinatura' dos dados de origem.
    Se a assinatura não mudou, o dia não precisa ser recalculado."""

    __tablename__ = "aulas_sincronizacao"

    data = Column(Date, primary_key=True)
    assinatura = Column(String(64), nullable=False)
    sincronizado_em = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
