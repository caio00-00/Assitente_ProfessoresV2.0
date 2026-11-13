"""
Canal Educação v3.0 — Modelo de Relatório de Aula (class_reports).
29 campos conforme especificação técnica v3.0.

v3.1: adiciona fluxo de validação de relatórios por Coordenação
(precisa_correcao, observacao_coordenacao, validado_por, validado_em).
"""

import uuid
from datetime import datetime, timezone
from app.core.config import get_settings

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import JSON
from sqlalchemy.orm import relationship, validates

from app.core.database import Base


class ClassReport(Base):
    __tablename__ = "class_reports"

    # Uniqueness enforced via partial index in DB (WHERE is_deleted = FALSE)
    # See migration: soft_delete_partial_unique_index

    # ─── A. Metadados do Registo (Automáticos) ───────────────────────
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    status = Column(
        String(30), default="RASCUNHO", nullable=False
    )  # RASCUNHO, AGUARDANDO_VALIDACAO, VALIDADO, CANCELADO (FINALIZADO = legado)

    # ─── B. Contexto Operacional ─────────────────────────────────────
    data_aula = Column(Date, nullable=False)
    turno = Column(String(20), nullable=False)  # Manhã, Tarde, Noite
    estudio = Column(String(50), nullable=False)  # Estúdio 01..09, Externo
    turma_id = Column(UUID(as_uuid=True), ForeignKey("turmas.id"), nullable=False)
    disciplina_id = Column(
        UUID(as_uuid=True), ForeignKey("disciplinas.id"), nullable=False
    )
    professor_id = Column(
        UUID(as_uuid=True), ForeignKey("professores.id"), nullable=True
    )
    professor_nome_externo = Column(String(255), nullable=True)
    horario_aula = Column(String(50), nullable=False)
    regular = Column(String(10), default="Sim", nullable=False)  # Sim / Não

    # ─── C. Detalhes da Execução ─────────────────────────────────────
    tipo_aula = Column(String(100), nullable=False)
    canal_utilizado = Column(String(50), nullable=False)
    conteudo_ministrado = Column(String(100), nullable=False)
    interacao_professor_aluno = Column(
        String(50), default="Não", nullable=False
    )
    interacao_outras_desc = Column(Text, nullable=True)
    atividade_pratica = Column(String(50), nullable=True)
    observacoes = Column(Text, nullable=True)

    # ─── D. Recursos e Materiais ─────────────────────────────────────
    tipo_recursos_utilizados = Column(JSON, nullable=True)  # Array de strings
    recursos_outro_desc = Column(Text, nullable=True)
    problema_material = Column(String(50), default="Não", nullable=False)
    problema_material_outro_desc = Column(Text, nullable=True)

    # ─── E. Ocorrências Operacionais ─────────────────────────────────
    teve_substituicao = Column(Boolean, default=False, nullable=False)
    professor_substituto_id = Column(
        UUID(as_uuid=True), ForeignKey("professores.id"), nullable=True
    )
    professor_substituto_nome_externo = Column(String(255), nullable=True)
    teve_atraso = Column(Boolean, default=False, nullable=False)
    minutos_atraso = Column(String(5), nullable=True) # TASK 13: HH:MM format (e.g. "00:10")
    observacao_atraso = Column(Text, nullable=True)

    # ─── F. Auditoria e Faturamento ──────────────────────────────────
    nome_ficheiro_gerado = Column(String(500), nullable=True)
    conflito_geminada_resolvido = Column(Boolean, default=False, nullable=False)
    
    # ─── G. Compliance Digital (§6) ──────────────────────────────────
    video_link = Column(String(1000), nullable=True)  # link do Drive (compliance)
    vimeo_link = Column(String(1000), nullable=True)  # link público do Vimeo (integração Vimeo Sync)
    status_compliance = Column(String(20), default="Pendente", nullable=False) # Verde, Vermelho, Pendente
    md5_checksum = Column(String(32), nullable=True)
    # v4.1: última vez que a busca no Drive olhou este relatório (a varredura
    # sem worker começa pelos que estão há mais tempo sem olhar)
    compliance_verificado_em = Column(DateTime(timezone=True), nullable=True)

    @property
    def video_folder_link(self) -> str:
        settings = get_settings()
        folder_id = settings.GOOGLE_DRIVE_VIDEOS_FOLDER_ID
        if not folder_id or folder_id == "id_pendente":
            return None
        return f"https://drive.google.com/drive/folders/{folder_id}"

    @property
    def creator_name(self) -> str:
        return self.creator.full_name if self.creator else "Desconhecido"

    @property
    def turma_nome(self) -> str:
        return self.turma.nomenclatura_padrao or self.turma.nome if self.turma else "N/A"

    @property
    def disciplina_nome(self) -> str:
        return self.disciplina.nome if self.disciplina else "N/A"

    @property
    def professor_nome(self) -> str:
        if self.professor:
            return self.professor.nome
        return self.professor_nome_externo or "—"

    @property
    def diretor_imagem_nome(self) -> str:
        return self.diretor_imagem_rel.nome if self.diretor_imagem_rel else "—"

    @property
    def validado_por_nome(self) -> str:
        return self.validador.full_name if self.validador else None

    # ─── H. Atualização v3.0 (Novos Campos) ──────────────────────────
    escolas_participantes = Column(JSON, nullable=True) # JSON array of strings
    diretor_imagem_id = Column(
        UUID(as_uuid=True), ForeignKey("diretores_imagem.id"), nullable=True
    )
    youtube_link = Column(String(1000), nullable=True)
    ticket_number = Column(String(100), nullable=True)
    needs_editing = Column(Boolean, default=False, nullable=False)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    problematic_materials = Column(JSON, nullable=True)
    observacoes_manha = Column(Text, nullable=True)
    bncc_habilidades = Column(Text, nullable=True) # Task 01: BNCC Skills as free text
    slide_link = Column(String(1000), nullable=True) # Task 02: Slide link
    is_deleted = Column(Boolean, default=False, server_default="false", nullable=False)

    # ─── J. Demandas Outubro 2026 (Antecipação e Mês de Referência) ────
    data_execucao_real = Column(Date, nullable=True)
    data_referencia_aula = Column(Date, nullable=True)
    solicitante_antecipacao = Column(String(20), nullable=True)  # SEDUC / PROFESSOR
    motivo_referencia = Column(String(255), nullable=True)

    # ─── I. Validação por Coordenação (v3.1) ─────────────────────────
    precisa_correcao = Column(Boolean, default=False, server_default="false", nullable=False)
    observacao_coordenacao = Column(Text, nullable=True)
    validado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    validado_em = Column(DateTime(timezone=True), nullable=True)

    # ─── K. v4 — cancelamento rastreável e chave de busca ────────────
    # Antes o cancelamento sobrescrevia "observacoes"; agora a justificativa
    # tem campo próprio e o texto original do assistente é preservado.
    justificativa_cancelamento = Column(Text, nullable=True)
    cancelado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    cancelado_em = Column(DateTime(timezone=True), nullable=True)
    # Nome do arquivo normalizado (sem acento, extensão e espaços), indexado:
    # usado pela rota do Vimeo e pelos verificadores no lugar de varrer a tabela.
    nome_normalizado = Column(String(500), nullable=True, index=True)

    # ─── Relationships ───────────────────────────────────────────────
    creator = relationship("User", foreign_keys=[created_by])
    turma = relationship("Turma")
    disciplina = relationship("Disciplina")
    professor = relationship("Professor", foreign_keys=[professor_id])
    professor_substituto = relationship(
        "Professor", foreign_keys=[professor_substituto_id]
    )
    diretor_imagem_rel = relationship("DiretorImagem")
    validador = relationship("User", foreign_keys=[validado_por])

    @validates("nome_ficheiro_gerado")
    def _sincronizar_nome_normalizado(self, key, value):
        # v4: mantém a chave de busca indexada sempre igual ao nome do arquivo
        from app.utils.text_utils import normalizar_para_match

        self.nome_normalizado = normalizar_para_match(value) if value else None
        return value

    @validates("conteudo_ministrado")
    def validate_conteudo_ministrado(self, key, value):
        if value is not None:
            return value.strip().upper()
        return value