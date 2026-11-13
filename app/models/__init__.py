"""
Canal Educação v3.0 — Models package init.
"""

from app.models.audit_log import AuditLog
from app.models.historico import LoginAttempt, ReportVersion
from app.models.auxiliares import (
    Disciplina,
    Grade,
    Professor,
    ProfessorDisciplina,
    Unit,
)
from app.models.class_report import ClassReport
from app.models.infraestrutura import Estudio, CanalIptvModel, SlotHorario, GradeVersao
from app.models.turma import Turma
from app.models.user import User
from app.models.diretor_imagem import DiretorImagem
from app.models.agenda_estudio import (  # noqa: F401
    AgendamentoEstudio, BloqueioEstudio, ConfigEstudioAgenda, EscalaDiaEstudio, EscalaFixaEstudio,
    FeriadoAgenda, ObservacaoAgenda,
)
from app.models.image_director_report import (
    ImageDirectorReport,
    ImageDirectorLesson,
    ImageDirectorChecklistItem,
    ImageDirectorChecklistResponse,
    ImageDirectorCustomQuestion,
    ImageDirectorCustomAnswer,
)
from app.models.aula import Aula, AulaSincronizacao  # noqa: F401  v5: a aula no centro

__all__ = [
    "AuditLog",
    "ReportVersion",
    "LoginAttempt",
    "User",
    "Turma",
    "ClassReport",
    "Professor",
    "Disciplina",
    "Grade",
    "Unit",
    "ProfessorDisciplina",
    "DiretorImagem",
    "AgendamentoEstudio",
    "BloqueioEstudio",
    "EscalaDiaEstudio",
    "EscalaFixaEstudio",
    "Estudio",
    "CanalIptvModel",
    "SlotHorario",
    "GradeVersao",
    "ImageDirectorReport",
    "ImageDirectorLesson",
    "ImageDirectorChecklistItem",
    "ImageDirectorChecklistResponse",
    "ImageDirectorCustomQuestion",
    "ImageDirectorCustomAnswer",
    "Aula",
    "AulaSincronizacao",
]
