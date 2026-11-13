"""
Canal Educação v3.2 — Relatório do Diretor de Imagem.

Reaproveita a mesma lógica do Relatório de Aula (ClassReport): metadados
automáticos, contexto operacional preenchido pelo diretor, uma lista de
itens de detalhe (aqui, uma "aula" por bloco, igual ao relatório manual em
papel usado hoje) e um fluxo simples de RASCUNHO -> FINALIZADO.

Estrutura:
  ImageDirectorReport        — cabeçalho (1 por diretor+data+turno+estúdio)
  ImageDirectorLesson        — detalhes técnicos de cada aula do turno
  ImageDirectorChecklistItem — catálogo de itens de fechamento de estúdio
                                (ex.: "Microfone", "Caneta", "Controle da TV"),
                                cadastrado pelo Diretor-Chefe
  ImageDirectorChecklistResponse — resposta (Sim/Não) de cada item, por relatório
  ImageDirectorCustomQuestion    — pergunta extra cadastrada pelo Diretor-Chefe
                                    (sim/não ou texto; por aula ou por relatório)
  ImageDirectorCustomAnswer      — resposta de uma pergunta extra
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class ImageDirectorReport(Base):
    """Cabeçalho do relatório: 1 diretor + 1 data + 1 turno + 1 estúdio (várias aulas dentro)."""

    __tablename__ = "image_director_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # ─── Metadados automáticos ────────────────────────────────────────
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    status = Column(String(20), default="RASCUNHO", nullable=False)  # RASCUNHO, AGUARDANDO_VALIDACAO, VALIDADO, CANCELADO
    finalized_at = Column(DateTime(timezone=True), nullable=True)

    # ─── Validação por Diretor-Chefe (mesma lógica do Relatório de Aula) ─
    precisa_correcao = Column(Boolean, default=False, server_default="false", nullable=False)
    observacao_coordenacao = Column(Text, nullable=True)
    validado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    validado_em = Column(DateTime(timezone=True), nullable=True)

    # ─── Contexto operacional (cabeçalho do exemplo em papel) ────────
    diretor_imagem_id = Column(
        UUID(as_uuid=True), ForeignKey("diretores_imagem.id"), nullable=False
    )
    data_relatorio = Column(Date, nullable=False)
    turno = Column(String(20), nullable=False)
    estudio = Column(String(50), nullable=False)
    turma_id = Column(UUID(as_uuid=True), ForeignKey("turmas.id"), nullable=True)
    serie_modulo_manual = Column(String(255), nullable=True)  # usado quando não há turma vinculada

    # v3.3 — identificação por slot da grade (1 relatório por horário/class_report)
    disciplina_id = Column(UUID(as_uuid=True), ForeignKey("disciplinas.id"), nullable=True)
    disciplina_nome = Column(String(255), nullable=True)
    professor_id = Column(UUID(as_uuid=True), ForeignKey("professores.id"), nullable=True)
    professor_nome_externo = Column(String(255), nullable=True)
    horario_aula = Column(String(100), nullable=True)
    regular = Column(String(10), default="Sim", server_default="Sim", nullable=False)
    ticket_number = Column(String(100), nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)

    horario_entrada = Column(Time, nullable=True)
    horario_saida = Column(Time, nullable=True)
    youtube_link = Column(String(1000), nullable=True)
    chave_transmissao = Column(String(255), nullable=True)

    # v3.5 — demandas outubro 2026 (eventos, antecipação e mês de referência)
    nome_evento = Column(String(255), nullable=True)
    departamento_solicitante = Column(String(120), nullable=True)
    responsavel_evento = Column(String(255), nullable=True)
    solicitante_antecipacao = Column(String(20), nullable=True)  # SEDUC / PROFESSOR
    data_referencia = Column(Date, nullable=True)
    motivo_referencia = Column(String(255), nullable=True)

    observacoes_gerais = Column(Text, nullable=True)
    is_deleted = Column(Boolean, default=False, server_default="false", nullable=False)

    # v3.4 — vínculo com relatório de aula + origem (grade | gravacao_estudio | nova_aula)
    class_report_id = Column(UUID(as_uuid=True), ForeignKey("class_reports.id"), nullable=True)
    origem = Column(String(30), default="grade", server_default="grade", nullable=False)

    # v4 — cancelamento rastreável (mesmo padrão do relatório de aula)
    justificativa_cancelamento = Column(Text, nullable=True)
    cancelado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    cancelado_em = Column(DateTime(timezone=True), nullable=True)

    # ─── Relationships ────────────────────────────────────────────────
    creator = relationship("User", foreign_keys=[created_by])
    validador = relationship("User", foreign_keys=[validado_por])
    diretor_imagem = relationship("DiretorImagem")
    turma = relationship("Turma")
    disciplina = relationship("Disciplina")
    professor = relationship("Professor", foreign_keys=[professor_id])
    class_report = relationship("ClassReport", foreign_keys=[class_report_id])
    lessons = relationship(
        "ImageDirectorLesson",
        back_populates="report",
        order_by="ImageDirectorLesson.numero_aula",
        cascade="all, delete-orphan",
    )
    checklist_respostas = relationship(
        "ImageDirectorChecklistResponse",
        back_populates="report",
        cascade="all, delete-orphan",
    )
    respostas_extras = relationship(
        "ImageDirectorCustomAnswer",
        back_populates="report",
        cascade="all, delete-orphan",
        foreign_keys="ImageDirectorCustomAnswer.report_id",
    )

    @property
    def diretor_imagem_nome(self) -> str:
        return self.diretor_imagem.nome if self.diretor_imagem else "—"

    @property
    def turma_nome(self) -> str:
        if self.turma:
            return self.turma.nomenclatura_padrao or self.turma.nome
        return self.serie_modulo_manual or "N/A"

    @property
    def professor_nome(self) -> str:
        if self.professor:
            return self.professor.nome
        if self.professor_nome_externo:
            return self.professor_nome_externo
        if self.lessons:
            nome = (self.lessons[0].professor_nome or "").strip()
            if nome:
                return nome
        return "—"

    @property
    def creator_name(self) -> str:
        return self.creator.full_name if self.creator else "Desconhecido"

    @property
    def validado_por_nome(self) -> str:
        return self.validador.full_name if self.validador else None


class ImageDirectorLesson(Base):
    """Um bloco 'AULA 0X' dentro do relatório do turno."""

    __tablename__ = "image_director_lessons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    report_id = Column(
        UUID(as_uuid=True), ForeignKey("image_director_reports.id"), nullable=False
    )
    numero_aula = Column(Integer, nullable=False)  # 1, 2, 3... (AULA 01, AULA 02...)

    # Vínculo opcional com o relatório de aula já lançado (auto-preenchimento)
    class_report_id = Column(UUID(as_uuid=True), ForeignKey("class_reports.id"), nullable=True)

    disciplina_nome = Column(String(255), nullable=False)
    professor_nome = Column(String(255), nullable=False)
    canal_utilizado = Column(String(50), nullable=True)

    # ─── Detalhamento técnico da aula (fixo, igual ao exemplo em papel) ──
    transmissao_ou_gravada = Column(String(20), nullable=False)  # "Transmissão" / "Aula gravada"
    video_corrompido = Column(String(10), default="Não", nullable=False)  # Sim/Não
    video_corrompido_obs = Column(Text, nullable=True)  # obrigatório quando video_corrompido = "Sim"
    interrupcoes = Column(String(10), default="Não", nullable=False)      # Sim/Não
    problema_audio = Column(String(10), default="Não", nullable=False)    # Sim/Não
    problema_audio_obs = Column(Text, nullable=True)  # obrigatório quando problema_audio = "Sim"
    vinhetas_corretas = Column(String(10), default="Sim", nullable=False)  # Sim/Não
    vinhetas_corretas_obs = Column(Text, nullable=True)  # obrigatório quando vinhetas_corretas = "Não"
    creditos_corretos = Column(String(10), default="Sim", nullable=False)  # Sim/Não

    observacoes = Column(Text, nullable=True)  # campo livre — ex.: marcações de tempo
    numero_chamado = Column(String(32), nullable=True)  # obrigatório quando aula gravada

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # ─── Relationships ────────────────────────────────────────────────
    report = relationship("ImageDirectorReport", back_populates="lessons")
    class_report = relationship("ClassReport")
    respostas_extras = relationship(
        "ImageDirectorCustomAnswer",
        back_populates="lesson",
        cascade="all, delete-orphan",
        foreign_keys="ImageDirectorCustomAnswer.lesson_id",
    )


class ImageDirectorChecklistItem(Base):
    """
    Catálogo de itens do checklist de fechamento de estúdio
    (ex.: 'Microfone', 'Caneta', 'Controle da TV na mesa').
    Cadastrado/mantido pelo Diretor-Chefe em /diretor-imagem/perguntas.
    """

    __tablename__ = "image_director_checklist_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    nome = Column(String(255), nullable=False)
    ativo = Column(Boolean, default=True, nullable=False)
    ordem = Column(Integer, default=0, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class ImageDirectorChecklistResponse(Base):
    """Resposta (Sim/Não) de um item do checklist, por relatório."""

    __tablename__ = "image_director_checklist_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    report_id = Column(
        UUID(as_uuid=True), ForeignKey("image_director_reports.id"), nullable=False
    )
    item_id = Column(
        UUID(as_uuid=True), ForeignKey("image_director_checklist_items.id"), nullable=False
    )
    resposta = Column(Boolean, nullable=True)  # True = presente/OK, False = faltando/problema

    report = relationship("ImageDirectorReport", back_populates="checklist_respostas")
    item = relationship("ImageDirectorChecklistItem")


class ImageDirectorCustomQuestion(Base):
    """
    Pergunta extra cadastrada pelo Diretor-Chefe, para além dos campos fixos
    do relatório. Pode ser do tipo Sim/Não ou texto livre, e aparecer uma vez
    por relatório ou repetida em cada bloco de aula.
    """

    __tablename__ = "image_director_custom_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    texto = Column(Text, nullable=False)
    tipo = Column(String(20), nullable=False, default="sim_nao")  # sim_nao | texto
    nivel = Column(String(20), nullable=False, default="por_relatorio")  # por_aula | por_relatorio
    obrigatoria = Column(Boolean, default=False, nullable=False)
    ativa = Column(Boolean, default=True, nullable=False)
    ordem = Column(Integer, default=0, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    creator = relationship("User", foreign_keys=[created_by])


class ImageDirectorCustomAnswer(Base):
    """Resposta de uma pergunta extra — vinculada ao relatório (por_relatorio) ou à aula (por_aula)."""

    __tablename__ = "image_director_custom_answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    question_id = Column(
        UUID(as_uuid=True), ForeignKey("image_director_custom_questions.id"), nullable=False
    )
    report_id = Column(
        UUID(as_uuid=True), ForeignKey("image_director_reports.id"), nullable=True
    )
    lesson_id = Column(
        UUID(as_uuid=True), ForeignKey("image_director_lessons.id"), nullable=True
    )
    resposta_texto = Column(Text, nullable=True)
    resposta_bool = Column(Boolean, nullable=True)

    question = relationship("ImageDirectorCustomQuestion")
    report = relationship(
        "ImageDirectorReport", back_populates="respostas_extras", foreign_keys=[report_id]
    )
    lesson = relationship(
        "ImageDirectorLesson", back_populates="respostas_extras", foreign_keys=[lesson_id]
    )
