"""
Canal Educação v3.0 — Schemas de Relatório de Aula (ClassReport).
DTOs Pydantic com validação completa conforme spec v3.0.
Inclui PaginatedReportsResponse para server-side pagination (§5.3).

v3.1: adiciona campos e schema de entrada do fluxo de validação por Coordenação.
"""

from datetime import date, datetime, time
from typing import List, Optional, Any
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator


class ClassReportCreate(BaseModel):
    """
    Request para criar um relatório de aula (rascunho).
    Campos do contexto operacional (B) podem vir auto-preenchidos pelo frontend.
    """

    # --- B. Contexto Operacional ---
    data_aula: date
    turno: str
    estudio: str
    turma_id: UUID
    disciplina_id: UUID
    professor_id: Optional[UUID] = None
    horario_aula: str
    regular: str = "Sim"

    # --- C. Detalhes da Execução ---
    tipo_aula: str
    canal_utilizado: str
    conteudo_ministrado: str
    interacao_professor_aluno: str = "Não"
    interacao_outras_desc: Optional[str] = None
    atividade_pratica: Optional[str] = None
    observacoes: Optional[str] = None

    # --- D. Recursos e Materiais ---
    tipo_recursos_utilizados: List[str]
    recursos_outro_desc: Optional[str] = None
    problema_material: str = "Não"
    problema_material_outro_desc: Optional[str] = None

    # --- E. Ocorrências Operacionais ---
    teve_substituicao: bool = False
    professor_substituto_id: Optional[UUID] = None
    professor_substituto_nome_externo: Optional[str] = None
    teve_atraso: bool = False
    minutos_atraso: Optional[str] = None # TASK 13: HH:MM format
    observacao_atraso: Optional[str] = None

    # --- F. Atualização v3.0 (Novos Campos) ---
    escolas_participantes: Optional[List[str]] = None
    diretor_imagem_id: Optional[UUID] = None
    professor_nome_externo: Optional[str] = None
    youtube_link: str
    ticket_number: Optional[str] = None
    needs_editing: bool = False
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    problematic_materials: Optional[Any] = None
    observacoes_manha: Optional[str] = None
    bncc_habilidades: str
    slide_link: Optional[str] = None

    # --- G. Demandas Outubro 2026 (Antecipação e Mês de Referência) ---
    data_execucao_real: Optional[date] = None
    data_referencia_aula: Optional[date] = None
    solicitante_antecipacao: Optional[str] = None
    motivo_referencia: Optional[str] = None

    @field_validator("professor_id", "professor_substituto_id", mode="before")
    @classmethod
    def validate_professor_id(cls, v):
        # Transforma o envio do Front "outro" ou vazio para nulo
        if v == "outro" or v == "":
            return None
        return v

    @field_validator("conteudo_ministrado")
    @classmethod
    def validate_conteudo(cls, v: str) -> str:
        if len(v) > 100:
            raise ValueError("Conteúdo ministrado deve ter no máximo 100 caracteres.")
        return v.strip().upper()

    @field_validator("disciplina_id", mode="before")
    @classmethod
    def validate_disciplina_id(cls, v):
        if v is None or v == "":
            raise ValueError("Disciplina obrigatoria")
        return v

    @field_validator("tipo_aula", mode="before")
    @classmethod
    def validate_tipo_aula(cls, v):
        if v is None or v == "":
            raise ValueError("Tipo de Aula deve ser selecionado")
        return v

    @field_validator("canal_utilizado", mode="before")
    @classmethod
    def validate_canal_utilizado(cls, v):
        if v is None or v == "":
            raise ValueError("Canal Utilizado deve ser selecionado")
        return v

    @field_validator("youtube_link", mode="before")
    @classmethod
    def validate_youtube_link(cls, v):
        if v is None or v == "":
            return ""
        if not isinstance(v, str):
            raise ValueError("O campo Link do YouTube deve ser uma string válida.")
        return v.strip()

    @field_validator("bncc_habilidades", mode="before")
    @classmethod
    def validate_bncc_habilidades(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError("O campo Habilidades BNCC / Currículo Piauí é obrigatório.")
        if not isinstance(v, str):
            raise ValueError("O campo Habilidades BNCC / Currículo Piauí é obrigatório.")
        return v.strip()

    @field_validator("tipo_recursos_utilizados", mode="before")
    @classmethod
    def validate_list_resources(cls, v):
        # Normaliza a entrada para evitar erro de tipo do Pydantic
        if v is None or v == "" or v == []:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("tipo_recursos_utilizados")
    @classmethod
    def check_not_empty(cls, v):
        if not v or len(v) == 0:
            raise ValueError("Por favor, selecione ao menos um recurso utilizado.")
        return v

    @field_validator("minutos_atraso")
    @classmethod
    def validate_minutos(cls, v: Optional[str]) -> Optional[str]:
        # Task 13: Novo formato HH:MM (ex: "00:10"). 
        # Aceita qualquer string validada pelo front, opcional se vazio.
        if v == "": return None
        return v

    @model_validator(mode="after")
    def validate_cross_fields(self):
        # Houve atraso -> necessita minutos_atraso e observacao_atraso
        if self.teve_atraso:
            if not self.minutos_atraso or self.minutos_atraso == "00:00":
                raise ValueError("Tempo de atraso é obrigatório quando houve atraso.")
            if not self.observacao_atraso:
                raise ValueError("Justificativa de atraso é obrigatória.")

        # Houve Substituição -> necessita professor cadastrado
        if self.teve_substituicao:
            if not self.professor_substituto_id:
                raise ValueError("Professor substituto é obrigatório quando houve substituição.")
            if self.professor_substituto_nome_externo:
                raise ValueError("Nome de substituto externo não é permitido. Cadastre o professor no sistema.")

        # Problema com material -> necessita problematic_materials
        if self.problema_material == "Sim":
            if not self.problematic_materials or len(self.problematic_materials) == 0:
                raise ValueError("Descrição do material problemático é obrigatória.")

        # Professor cadastrado (aulas regulares)
        if self.regular != "Não":
            if not self.professor_id:
                raise ValueError("Professor é obrigatório. Selecione um professor cadastrado.")
            if self.professor_nome_externo:
                raise ValueError("Nome de professor externo não é permitido. Cadastre o professor no sistema.")

        return self


class ClassReportFinalize(BaseModel):
    """Request para finalizar um relatório (muda status para AGUARDANDO_VALIDACAO)."""

    pass


class ClassReportCancel(BaseModel):
    """Request para cancelar um relatório."""

    justificativa: str


class ClassReportSolicitarCorrecao(BaseModel):
    """
    v3.1 — Request da Coordenação para devolver um relatório ao Assistente.
    O relatório volta para RASCUNHO com precisa_correcao=True.
    """

    observacao_coordenacao: str

    @field_validator("observacao_coordenacao")
    @classmethod
    def validate_observacao(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("É necessário descrever o motivo da correção.")
        return v.strip()


def _coerce_json_string_list(v: Any) -> Optional[List[str]]:
    """Normaliza colunas JSON legadas (string/dict) para lista de strings."""
    if v is None:
        return None
    if isinstance(v, list):
        return [str(x) for x in v if x is not None and str(x).strip()]
    if isinstance(v, str):
        return [v] if v.strip() else []
    if isinstance(v, dict):
        return [str(x) for x in v.values() if x is not None and str(x).strip()]
    return [str(v)]


class ClassReportResponse(BaseModel):
    """Response completa de um relatório de aula."""

    # A. Metadados
    id: UUID
    created_by: UUID
    created_at: datetime
    status: str
    creator_name: Optional[str] = None
    turma_nome: Optional[str] = "N/A"
    disciplina_nome: Optional[str] = "N/A"
    professor_nome: Optional[str] = "—"
    diretor_imagem_nome: Optional[str] = "—"

    # B. Contexto
    data_aula: date
    turno: str
    estudio: str
    turma_id: UUID
    disciplina_id: UUID
    professor_id: Optional[UUID] = None
    professor_nome_externo: Optional[str] = None
    horario_aula: str
    regular: str

    # C. Execução
    tipo_aula: str
    canal_utilizado: str
    conteudo_ministrado: str
    interacao_professor_aluno: str
    interacao_outras_desc: Optional[str] = None
    atividade_pratica: Optional[str] = None
    observacoes: Optional[str] = None

    # D. Recursos
    tipo_recursos_utilizados: Optional[List[str]] = None
    recursos_outro_desc: Optional[str] = None
    problema_material: str
    problema_material_outro_desc: Optional[str] = None

    # E. Ocorrências
    teve_substituicao: bool
    professor_substituto_id: Optional[UUID] = None
    professor_substituto_nome_externo: Optional[str] = None
    teve_atraso: bool
    minutos_atraso: Optional[str] = None
    observacao_atraso: Optional[str] = None

    # F. Auditoria
    nome_ficheiro_gerado: Optional[str] = None
    conflito_geminada_resolvido: bool

    # G. Compliance Digital (§6)
    video_link: Optional[str] = None
    video_folder_link: Optional[str] = None
    vimeo_link: Optional[str] = None  # link público do Vimeo (integração Vimeo Sync)
    status_compliance: str = "Pendente"

    # H. Atualização v3.0 (Novos Campos)
    escolas_participantes: Optional[List[str]] = None
    diretor_imagem_id: Optional[UUID] = None
    youtube_link: Optional[str] = None
    ticket_number: Optional[str] = None
    needs_editing: bool
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    problematic_materials: Optional[Any] = None
    observacoes_manha: Optional[str] = None
    bncc_habilidades: Optional[str] = None
    slide_link: Optional[str] = None

    # I. Validação por Coordenação (v3.1)
    precisa_correcao: bool = False
    observacao_coordenacao: Optional[str] = None
    validado_por: Optional[UUID] = None
    validado_por_nome: Optional[str] = None
    validado_em: Optional[datetime] = None

    # J. Relatório do Diretor de Imagem associado (v3.4)
    image_director_report_id: Optional[UUID] = None
    image_director_status: Optional[str] = None
    image_director_youtube_link: Optional[str] = None
    image_director_validado_por_nome: Optional[str] = None
    image_director_validado_em: Optional[datetime] = None
    image_director_precisa_correcao: Optional[bool] = None
    image_director_origem: Optional[str] = None
    image_director_diretor_nome: Optional[str] = None

    # K. Demandas Outubro 2026 (Antecipação e Mês de Referência)
    data_execucao_real: Optional[date] = None
    data_referencia_aula: Optional[date] = None
    solicitante_antecipacao: Optional[str] = None
    motivo_referencia: Optional[str] = None

    # L. Fila da coordenação (reunião out/2026): por que o relatório ainda não pode ser validado
    pronto_para_validar: Optional[bool] = None
    motivo_espera_validacao: Optional[str] = None

    @field_validator(
        "tipo_recursos_utilizados",
        "escolas_participantes",
        mode="before",
    )
    @classmethod
    def coerce_json_lists(cls, v: Any) -> Optional[List[str]]:
        return _coerce_json_string_list(v)

    @field_validator(
        "teve_substituicao",
        "teve_atraso",
        "conflito_geminada_resolvido",
        "needs_editing",
        "precisa_correcao",
        mode="before",
    )
    @classmethod
    def coerce_bool_fields(cls, v: Any) -> bool:
        if v is None:
            return False
        return bool(v)

    @field_validator("interacao_professor_aluno", "problema_material", mode="before")
    @classmethod
    def coerce_default_nao(cls, v: Any) -> str:
        if v is None or v == "":
            return "Não"
        return str(v)

    @field_validator("regular", mode="before")
    @classmethod
    def coerce_regular(cls, v: Any) -> str:
        if v is None or v == "":
            return "Sim"
        return str(v)

    @field_validator("status_compliance", mode="before")
    @classmethod
    def coerce_status_compliance(cls, v: Any) -> str:
        if v is None or v == "":
            return "Pendente"
        return str(v)

    @field_validator(
        "turno",
        "estudio",
        "horario_aula",
        "tipo_aula",
        "canal_utilizado",
        "conteudo_ministrado",
        "status",
        mode="before",
    )
    @classmethod
    def coerce_required_text(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    class Config:
        from_attributes = True


def serialize_class_report(report: Any, image_director: Any = None) -> ClassReportResponse:
    """Serializa ORM ClassReport → DTO (tolera dados legados no banco)."""
    dto = ClassReportResponse.model_validate(report, from_attributes=True)
    if image_director is not None:
        dto.image_director_report_id = image_director.id
        dto.image_director_status = image_director.status
        dto.image_director_youtube_link = image_director.youtube_link
        dto.image_director_validado_por_nome = image_director.validado_por_nome
        dto.image_director_validado_em = image_director.validado_em
        dto.image_director_precisa_correcao = image_director.precisa_correcao
        dto.image_director_origem = getattr(image_director, "origem", None)
        nome_dir = getattr(image_director, "diretor_imagem_nome", None)
        dto.image_director_diretor_nome = nome_dir if nome_dir and nome_dir != "—" else None
    if getattr(report, "status", None) == "AGUARDANDO_VALIDACAO":
        from app.services.busca_links import motivo_espera_validacao

        motivo = motivo_espera_validacao(report, image_director)
        dto.pronto_para_validar = motivo is None
        dto.motivo_espera_validacao = motivo
    return dto


class PaginatedReportsResponse(BaseModel):
    """Response paginada para listagem de relatórios (§5.3)."""
    items: List[ClassReportResponse]
    total: int
    limit: int
    offset: int