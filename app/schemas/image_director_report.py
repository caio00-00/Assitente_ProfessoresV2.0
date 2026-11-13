"""
Canal Educação v3.2 — Schemas do Relatório do Diretor de Imagem.
"""

from datetime import date, datetime, time
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

from app.utils.text_utils import is_placeholder_professor


# ─── Lições (blocos "AULA 0X") ─────────────────────────────────────────

class ExistingReportLookup(BaseModel):
    id: str
    status: str


class NumeroAulaLookup(BaseModel):
    numero_aula: int


class ImageDirectorLessonCreate(BaseModel):
    class_report_id: Optional[UUID] = None
    disciplina_nome: str
    professor_nome: str
    canal_utilizado: Optional[str] = None
    transmissao_ou_gravada: str
    video_corrompido: str = "Não"
    video_corrompido_obs: Optional[str] = None
    interrupcoes: str = "Não"
    problema_audio: str = "Não"
    problema_audio_obs: Optional[str] = None
    vinhetas_corretas: str = "Sim"
    vinhetas_corretas_obs: Optional[str] = None
    creditos_corretos: str = "Sim"
    observacoes: Optional[str] = None
    numero_chamado: Optional[str] = None
    numero_aula: Optional[int] = None

    @field_validator("disciplina_nome")
    @classmethod
    def disciplina_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Campo obrigatório.")
        return v.strip()

    @field_validator("professor_nome")
    @classmethod
    def professor_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Campo obrigatório.")
        cleaned = v.strip()
        if is_placeholder_professor(cleaned):
            raise ValueError("Informe o nome real do professor (N/A não é aceito).")
        return cleaned

    @model_validator(mode="after")
    def validate_canal_ou_chamado(self):
        if self.transmissao_ou_gravada == "Transmissão":
            # Reunião (out/2026): o canal vem da Agenda (diretor-chefe). Transmissão só pelo
            # YouTube não tem canal IPTV — fica vazio. O formulário cobra o canal quando a aula
            # não veio da Agenda.
            self.canal_utilizado = (self.canal_utilizado or "").strip() or None
        elif self.transmissao_ou_gravada == "Aula gravada":
            self.canal_utilizado = None
        return self

    @model_validator(mode="after")
    def validate_justificativas(self):
        if self.video_corrompido == "Sim" and not (self.video_corrompido_obs or "").strip():
            raise ValueError("Descreva o problema do vídeo corrompido.")
        if self.problema_audio == "Sim" and not (self.problema_audio_obs or "").strip():
            raise ValueError("Descreva o problema de áudio.")
        if self.vinhetas_corretas == "Não" and not (self.vinhetas_corretas_obs or "").strip():
            raise ValueError("Descreva o problema com as vinhetas.")
        if self.transmissao_ou_gravada == "Aula gravada":
            nc = (self.numero_chamado or "").strip()
            if nc:
                if not nc.isdigit():
                    raise ValueError("Nº chamado deve conter somente números.")
                self.numero_chamado = nc
            else:
                self.numero_chamado = None
        return self


class ImageDirectorLessonResponse(BaseModel):
    id: UUID
    report_id: UUID
    numero_aula: int
    created_at: datetime
    class_report_id: Optional[UUID] = None
    disciplina_nome: str
    professor_nome: str
    canal_utilizado: Optional[str] = None
    transmissao_ou_gravada: str
    video_corrompido: str = "Não"
    video_corrompido_obs: Optional[str] = None
    interrupcoes: str = "Não"
    problema_audio: str = "Não"
    problema_audio_obs: Optional[str] = None
    vinhetas_corretas: str = "Sim"
    vinhetas_corretas_obs: Optional[str] = None
    creditos_corretos: str = "Sim"
    observacoes: Optional[str] = None
    numero_chamado: Optional[str] = None

    class Config:
        from_attributes = True


# ─── Checklist de fechamento de estúdio ────────────────────────────────

class ChecklistItemCreate(BaseModel):
    nome: str
    ordem: int = 0

    @field_validator("nome")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Nome do item é obrigatório.")
        return v.strip()


class ChecklistItemUpdate(BaseModel):
    nome: Optional[str] = None
    ordem: Optional[int] = None
    ativo: Optional[bool] = None


class ChecklistItemResponse(BaseModel):
    id: UUID
    nome: str
    ativo: bool
    ordem: int

    class Config:
        from_attributes = True


class ChecklistAnswerIn(BaseModel):
    item_id: UUID
    resposta: Optional[bool] = None


# ─── Perguntas extras (cadastradas pelo Diretor-Chefe) ─────────────────

class CustomQuestionCreate(BaseModel):
    texto: str
    tipo: str = "sim_nao"       # sim_nao | texto
    nivel: str = "por_relatorio"  # por_aula | por_relatorio
    obrigatoria: bool = False
    ordem: int = 0

    @field_validator("texto")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Texto da pergunta é obrigatório.")
        return v.strip()

    @field_validator("tipo")
    @classmethod
    def valid_tipo(cls, v: str) -> str:
        if v not in ("sim_nao", "texto"):
            raise ValueError("Tipo deve ser 'sim_nao' ou 'texto'.")
        return v

    @field_validator("nivel")
    @classmethod
    def valid_nivel(cls, v: str) -> str:
        if v not in ("por_aula", "por_relatorio"):
            raise ValueError("Nível deve ser 'por_aula' ou 'por_relatorio'.")
        return v


class CustomQuestionUpdate(BaseModel):
    texto: Optional[str] = None
    tipo: Optional[str] = None
    nivel: Optional[str] = None
    obrigatoria: Optional[bool] = None
    ativa: Optional[bool] = None
    ordem: Optional[int] = None


class CustomQuestionResponse(BaseModel):
    id: UUID
    texto: str
    tipo: str
    nivel: str
    obrigatoria: bool
    ativa: bool
    ordem: int

    class Config:
        from_attributes = True


class CustomAnswerIn(BaseModel):
    question_id: UUID
    lesson_id: Optional[UUID] = None  # obrigatório se a pergunta for "por_aula"
    resposta_texto: Optional[str] = None
    resposta_bool: Optional[bool] = None


class CustomAnswerResponse(BaseModel):
    id: UUID
    question_id: UUID
    lesson_id: Optional[UUID] = None
    resposta_texto: Optional[str] = None
    resposta_bool: Optional[bool] = None

    class Config:
        from_attributes = True


# ─── Relatório (cabeçalho do turno) ─────────────────────────────────────

def _validate_contexto_operacional(regular: str, horario_aula: Optional[str], ticket_number: Optional[str], start_time, end_time):
    if regular == "Não":
        if not ticket_number or not str(ticket_number).strip():
            raise ValueError("Campo 'ticket_number' é obrigatório para aulas NÃO regulares (avulsas).")
        if not start_time or not end_time:
            raise ValueError("Campos 'start_time' e 'end_time' são obrigatórios para aulas avulsas.")
    elif not horario_aula or not str(horario_aula).strip():
        raise ValueError("Campo 'horario_aula' é obrigatório para aulas regulares.")


class ImageDirectorReportCreate(BaseModel):
    diretor_imagem_id: UUID
    data_relatorio: date
    turno: str
    estudio: str
    turma_id: Optional[UUID] = None
    serie_modulo_manual: Optional[str] = None
    disciplina_id: Optional[UUID] = None
    disciplina_nome: Optional[str] = None
    professor_id: Optional[UUID] = None
    professor_nome_externo: Optional[str] = None
    horario_aula: Optional[str] = None
    regular: str = "Sim"
    ticket_number: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    horario_entrada: Optional[time] = None
    horario_saida: Optional[time] = None
    youtube_link: Optional[str] = None
    chave_transmissao: Optional[str] = None
    nome_evento: Optional[str] = None
    departamento_solicitante: Optional[str] = None
    responsavel_evento: Optional[str] = None
    solicitante_antecipacao: Optional[str] = None
    data_referencia: Optional[date] = None
    motivo_referencia: Optional[str] = None
    observacoes_gerais: Optional[str] = None
    origem: str = "grade"
    class_report_id: Optional[UUID] = None

    @field_validator("origem")
    @classmethod
    def valid_origem(cls, v: str) -> str:
        if v == "nova_aula":
            raise ValueError("A opção Nova Aula foi retirada: lance o relatório a partir da aula na Grade Horária.")
        allowed = {"grade", "gravacao_estudio", "evento"}
        if v not in allowed:
            raise ValueError(f"origem deve ser um de: {', '.join(sorted(allowed))}")
        return v

    @field_validator("youtube_link")
    @classmethod
    def youtube_valido(cls, v: Optional[str]) -> Optional[str]:
        if not v or not str(v).strip():
            return None
        url = str(v).strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("Link do YouTube inválido. Use uma URL completa (https://...).")
        return url

    @model_validator(mode="after")
    def validate_serie(self):
        if self.origem == "evento":
            # Evento (UETEV, SUGED…): sem turma/professor; nome do evento vai em
            # disciplina_nome e o departamento em serie_modulo_manual.
            if not (self.disciplina_nome or "").strip():
                raise ValueError("Informe o nome do evento.")
            if not (self.serie_modulo_manual or "").strip():
                raise ValueError("Informe o departamento/solicitante do evento.")
            _validate_contexto_operacional(
                "Não", self.horario_aula, self.ticket_number, self.start_time, self.end_time
            )
            return self
        if not self.turma_id and not self.serie_modulo_manual:
            raise ValueError("Informe a turma/série (selecionada ou digitada).")
        if not self.disciplina_id and not (self.disciplina_nome or "").strip():
            raise ValueError("Informe a disciplina.")
        if not self.professor_id:
            ext = (self.professor_nome_externo or "").strip()
            if not ext or is_placeholder_professor(ext):
                raise ValueError("Informe o professor.")
        _validate_contexto_operacional(
            self.regular, self.horario_aula, self.ticket_number, self.start_time, self.end_time
        )
        return self


class ImageDirectorReportUpdate(BaseModel):
    turno: Optional[str] = None
    estudio: Optional[str] = None
    turma_id: Optional[UUID] = None
    serie_modulo_manual: Optional[str] = None
    disciplina_id: Optional[UUID] = None
    disciplina_nome: Optional[str] = None
    professor_id: Optional[UUID] = None
    professor_nome_externo: Optional[str] = None
    horario_aula: Optional[str] = None
    regular: Optional[str] = None
    ticket_number: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    horario_entrada: Optional[time] = None
    horario_saida: Optional[time] = None
    youtube_link: Optional[str] = None
    chave_transmissao: Optional[str] = None
    nome_evento: Optional[str] = None
    departamento_solicitante: Optional[str] = None
    responsavel_evento: Optional[str] = None
    solicitante_antecipacao: Optional[str] = None
    data_referencia: Optional[date] = None
    motivo_referencia: Optional[str] = None
    observacoes_gerais: Optional[str] = None

    @model_validator(mode="after")
    def validate_contexto(self):
        if self.regular is not None or self.horario_aula is not None:
            regular = self.regular if self.regular is not None else "Sim"
            _validate_contexto_operacional(
                regular, self.horario_aula, self.ticket_number, self.start_time, self.end_time
            )
        return self


class ImageDirectorReportResponse(BaseModel):
    id: UUID
    created_by: UUID
    creator_name: Optional[str] = None
    created_at: datetime
    status: str
    finalized_at: Optional[datetime] = None

    # ─── Validação por Diretor-Chefe (mesma lógica do Relatório de Aula) ─
    precisa_correcao: bool = False
    observacao_coordenacao: Optional[str] = None
    validado_por: Optional[UUID] = None
    validado_por_nome: Optional[str] = None
    validado_em: Optional[datetime] = None

    diretor_imagem_id: UUID
    diretor_imagem_nome: Optional[str] = None
    data_relatorio: date
    turno: str
    estudio: str
    turma_id: Optional[UUID] = None
    turma_nome: Optional[str] = None
    serie_modulo_manual: Optional[str] = None
    disciplina_id: Optional[UUID] = None
    disciplina_nome: Optional[str] = None
    professor_id: Optional[UUID] = None
    professor_nome: Optional[str] = None
    horario_aula: Optional[str] = None
    regular: str = "Sim"
    ticket_number: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    horario_entrada: Optional[time] = None
    horario_saida: Optional[time] = None
    youtube_link: Optional[str] = None
    chave_transmissao: Optional[str] = None
    nome_evento: Optional[str] = None
    departamento_solicitante: Optional[str] = None
    responsavel_evento: Optional[str] = None
    solicitante_antecipacao: Optional[str] = None
    data_referencia: Optional[date] = None
    motivo_referencia: Optional[str] = None
    observacoes_gerais: Optional[str] = None
    origem: str = "grade"
    class_report_id: Optional[UUID] = None
    horario_ordinal: Optional[int] = None

    lessons: List[ImageDirectorLessonResponse] = []
    checklist_respostas: List[ChecklistAnswerIn] = []
    respostas_extras: List[CustomAnswerResponse] = []

    class Config:
        from_attributes = True


class ImageDirectorSolicitarCorrecao(BaseModel):
    """Diretor-Chefe/Coordenação envia o relatório de volta para correção."""
    observacao_coordenacao: str

    @field_validator("observacao_coordenacao")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Descreva o motivo da correção.")
        return v.strip()


class ImageDirectorFinalizeRequest(BaseModel):
    """Payload opcional ao finalizar — garante persistência do YouTube no momento do envio."""
    youtube_link: Optional[str] = None

    @field_validator("youtube_link")
    @classmethod
    def youtube_valido(cls, v: Optional[str]) -> Optional[str]:
        if not v or not str(v).strip():
            return None
        url = str(v).strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("Link do YouTube inválido. Use uma URL completa (https://...).")
        return url


class ImageDirectorReportListItem(BaseModel):
    """Item resumido para a listagem do histórico (sem nested lessons/checklist)."""

    id: UUID
    status: str
    precisa_correcao: bool = False
    diretor_imagem_id: UUID
    diretor_imagem_nome: Optional[str] = None
    data_relatorio: date
    turno: str
    estudio: str
    turma_id: Optional[UUID] = None
    turma_nome: Optional[str] = None
    aulas_count: int = 0
    origem: str = "grade"
    disciplina_id: Optional[UUID] = None
    disciplina_nome: Optional[str] = None
    professor_nome: Optional[str] = None
    horario_aula: Optional[str] = None
    # Horário exato do slot (HH:MM) resolvido pela grade/turno/modalidade
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    horario_faixa: Optional[str] = None
    horario_ordinal: Optional[int] = None  # nº da aula conforme grade (TI tarde = 5º...)
    regular: str = "Sim"
    # True quando o relatório corresponde a um slot da grade horária da turma
    # (inclui aulas REGULARES ainda sem ClassReport vinculado) → agrupa por turno.
    pertence_grade: bool = False
    turma_ti: bool = False
    class_report_id: Optional[UUID] = None
    # Relatórios "legado" (1 por turno, várias aulas dentro) não têm disciplina_id/
    # horario_aula/class_report_id no cabeçalho — cada ImageDirectorLesson é que
    # carrega o vínculo com o ClassReport da disciplina específica daquele horário.
    # Expor aqui permite que a Grade Horária identifique o status correto também
    # para essas disciplinas (comum em turmas não-técnicas), e não só para os
    # relatórios "por slot" (1 por disciplina/horário) usados pelas turmas técnicas.
    lesson_class_report_ids: List[UUID] = []
    youtube_link: Optional[str] = None
    validado_por_nome: Optional[str] = None
    # Resumo do ClassReport vinculado (auditoria — evita status "Pendente" falso na mesclagem)
    class_report_status: Optional[str] = None
    class_report_status_compliance: Optional[str] = None
    class_report_nome_ficheiro_gerado: Optional[str] = None
    class_report_video_link: Optional[str] = None
    class_report_slide_link: Optional[str] = None
    class_report_creator_name: Optional[str] = None
    class_report_validado_por_nome: Optional[str] = None
    class_report_precisa_correcao: Optional[bool] = None

    class Config:
        from_attributes = True


class PaginatedImageDirectorReports(BaseModel):
    items: List[ImageDirectorReportListItem]
    total: int
    limit: int
    offset: int

    class Config:
        from_attributes = True
