"""
Canal Educação v3.0 — Schemas da API Externa M2M (Estudologia).
Modelos Pydantic para os endpoints /api/v1/external/habilidades/*.
"""

from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


# ─── Modelos Base ────────────────────────────────────────────────────


class HabilidadeDetalhe(BaseModel):
    """Uma habilidade BNCC estruturada com código e descrição."""

    codigo: str
    descricao: str


# ─── Retorno por Ficheiro ─────────────────────────────────────────────


class RelatorioHabilidadeResponse(BaseModel):
    """Habilidades vinculadas a um relatório específico (por report_id)."""

    report_id: UUID
    ficheiro_nome: Optional[str]
    total_habilidades: int
    habilidades: List[HabilidadeDetalhe]

    class Config:
        from_attributes = True


# ─── Retorno por Turma ────────────────────────────────────────────────


class TurmaHabilidadesAgregadas(BaseModel):
    """Agregação de habilidades por turma (contagem de ocorrências por código)."""

    turma_id: UUID
    turma_nome: Optional[str]
    periodo_letivo: str
    habilidades_mapeadas: Dict[str, int]

    class Config:
        from_attributes = True


# ─── Retorno por Disciplina ───────────────────────────────────────────


class DisciplinaHabilidadesResponse(BaseModel):
    """Códigos BNCC distintos associados a uma disciplina."""

    disciplina: str
    total_codigos_distintos: int
    habilidades: List[str]

    class Config:
        from_attributes = True


# ─── Retorno por Período ──────────────────────────────────────────────


class PeriodoItemResponse(BaseModel):
    """Item individual de habilidade por período."""

    report_id: UUID
    codigo: str
    descricao: str
    data_aula: date

    class Config:
        from_attributes = True


class PeriodoHabilidadesResponse(BaseModel):
    """Habilidades registradas em um determinado período."""

    periodo: str
    total_habilidades_periodo: int
    data_extracao: datetime
    itens: List[PeriodoItemResponse]

    class Config:
        from_attributes = True


# ─── Integração Vimeo Sync (recebe link do vídeo) ─────────────────────


class VimeoLinkInput(BaseModel):
    """Payload enviado pelo Vimeo Sync quando um vídeo termina (SUCCESS)."""

    nome_ficheiro: str
    vimeo_url: str
    vimeo_uri: Optional[str] = None
    # Link de visualização do MESMO arquivo no Google Drive (opcional).
    # Quando presente, é gravado em class_reports.video_link se ainda estiver vazio.
    drive_url: Optional[str] = None


class VimeoLinkResponse(BaseModel):
    """Resultado do casamento por nome de arquivo (resposta 200)."""

    status: str  # "vinculado"
    matched: bool
    updated: int
    drive_updated: int = 0
    report_ids: List[UUID] = []
    nome_ficheiro: str


# ─── Planilhas de Cursos Técnicos (preenchimento por disciplina) ──────


class AulaLinha(BaseModel):
    """Uma linha da planilha: o arquivo da aula e seus links."""

    nome_arquivo: str
    vimeo_url: str = ""
    drive_url: str = ""
    pdf_url: str = ""


class AulasPorDisciplinaResponse(BaseModel):
    """Aulas (linhas) de uma disciplina, para preencher a aba da planilha."""

    disciplina_consultada: str
    disciplina_casada: Optional[str] = None  # nome no banco; None se não casou
    total: int
    linhas: List[AulaLinha] = []
