"""
Canal Educação v3.0 — Rotas de Relatórios de Aula (Class Reports).
CRUD completo com auto-preenchimento, validação relacional,
campos condicionais, Naming Engine, paginação server-side e exportação CSV.

v3.1: adiciona fluxo de validação de relatórios por Coordenação
(AGUARDANDO_VALIDACAO -> VALIDADO / devolvido para correção).
"""

import csv
import io
import os
import json
import re
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_active_user, require_class_report_access, require_class_report_write, require_role
from app.domain import estados, politicas
from app.services.grade_vigente import slots_da_turma_no_dia
from app.utils.text_utils import normalizar_para_match
from app.services.historico import TIPO_AULA, registrar_versao
from app.core.database import get_db
from app.models.auxiliares import Disciplina, Professor, ProfessorDisciplina, Grade
from app.models.diretor_imagem import DiretorImagem
from app.models.class_report import ClassReport
from app.models.turma import Turma
from app.models.user import User
from app.models.audit_log import AuditLog
from app.schemas.class_report import (
    ClassReportCancel,
    ClassReportCreate,
    ClassReportResponse,
    ClassReportSolicitarCorrecao,
    PaginatedReportsResponse,
    serialize_class_report,
)
from app.services.naming_engine import (
    gerar_nome_padronizado,
    verificar_sufixo_geminada,
)
from app.services.image_director_associacao import (
    buscar_image_director_por_class_report,
    divergencias_do_par,
    vincular_image_director_ao_class_report,
    validar_consistencia_faturamento,
    gerar_indicativo_reposicao,
    ajustar_datas_gravacao,
)
from sqlalchemy import or_, and_, func, not_
from datetime import datetime, time, timezone
import asyncio

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["Relatórios de Aula"],
)

# v4: escrita bloqueia diretores E auditor (antes o auditor conseguia escrever)
_WRITE_DEPS = [Depends(require_class_report_write)]

# Papéis com permissão para validar/devolver relatórios para correção (v3.1)
PAPEIS_COORDENACAO = ("admin", "gestor", "coordenador")

# Status considerados "não-rascunho" para fins de compliance/geminada/grade —
# cobre o fluxo novo (AGUARDANDO_VALIDACAO/VALIDADO) e dados antigos (FINALIZADO).
STATUS_FINALIZADOS = ("FINALIZADO", "AGUARDANDO_VALIDACAO", "VALIDADO")

# Conteúdo ministrado: mesmo limite do formulário (o nome do arquivo sai dele)
LIMITE_CONTEUDO_MINISTRADO = 87


def _mesmo_horario(a, b) -> bool:
    """Dois relatórios da mesma turma/disciplina/data no mesmo horário = mesma aula."""
    if a.start_time and b.start_time:
        return a.start_time == b.start_time
    ha = (a.horario_aula or "").strip().lower()
    hb = (b.horario_aula or "").strip().lower()
    return bool(ha) and ha == hb


def _chave_horario(r):
    """Ordena pelo início da aula; sem início, pelo número do horário ("4º Horário")."""
    import re as _re
    if r.start_time:
        return (0, r.start_time.hour * 60 + r.start_time.minute)
    m = _re.match(r"\s*(\d+)", r.horario_aula or "")
    return (1, int(m.group(1)) if m else 99)


def _sufixo_geminada(report, outras) -> str:
    """P1, P2 ou P3 pela posição do horário desta aula entre as aulas da disciplina no dia."""
    ordem = sorted([report, *outras], key=_chave_horario)
    pos = next(i for i, r in enumerate(ordem) if r is report)
    return f"P{min(pos + 1, 3)}"

# Tipos de aula "especiais" — não seguem a grade oficial nem entram nas
# validações de choque/duplicidade/geminada, pois usam estúdio/canal/horário
# fora do padrão de aula regular. Usar SEMPRE esta constante (não recriar a
# tupla solta em outros pontos) para não repetir o bug de um tipo ficar de
# fora de alguma validação por engano.
TIPOS_ESPECIAIS = ("Gravação estúdio", "Gravação externa", "Manutenção de estúdio")


from app.services.horario_resolver import (
    HORARIO_MAP,
    get_tipo_por_turno as _get_tipo_por_turno,
    get_tipo_turma as _get_tipo_turma,
    resolver_horario as _resolver_horario,
)


# ─── Validação de Campos Condicionais ────────────────────────────────


def _validar_campos_condicionais(data: ClassReportCreate) -> None:
    """
    Validação relaxada para RASCUNHOS (TASK 09).
    Permite salvar rascunhos sem campos obrigatórios condicionais.
    As validações rígidas foram movidas para 'finalizar_relatorio'.
    """
    pass

    if data.regular == "Não":
        if not data.ticket_number:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Campo 'ticket_number' é obrigatório para aulas NÃO regulares (avulsas).",
            )
        if not data.start_time or not data.end_time:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Campos 'start_time' e 'end_time' são obrigatórios para aulas avulsas.",
            )



# ─── Clash Detection (Choque de Horário) ────────────────────────────

def _formatar_detalhe_conflito_report(r: ClassReport) -> str:
    if r.start_time and r.end_time:
        horario_txt = f"{r.start_time.strftime('%H:%M')} às {r.end_time.strftime('%H:%M')}"
    elif r.horario_aula:
        horario_txt = r.horario_aula
    else:
        horario_txt = "N/A"
    data_txt = r.data_aula.strftime("%d/%m/%Y") if r.data_aula else "N/A"
    return (
        f"Turma: {r.turma_nome or 'N/A'}\n"
        f"Disciplina: {r.disciplina_nome or 'N/A'}\n"
        f"Estúdio: {r.estudio or 'N/A'}\n"
        f"Canal: {r.canal_utilizado or 'N/A'}\n"
        f"Tipo: {r.tipo_aula or 'N/A'}\n"
        f"Data: {data_txt}\n"
        f"Horário: {horario_txt}\n"
        f"Status: {(r.status or 'N/A').upper()}"
    )


def _formatar_mensagem_choque_horario(reports: list, cabecalho: str) -> str:
    blocos = [_formatar_detalhe_conflito_report(r) for r in reports[:3]]
    conflitos_txt = "\n\n".join(blocos)
    return f"{cabecalho}\nConflito(s):\n{conflitos_txt}"


def _tipos_competem_choque(tipo_a: Optional[str], tipo_b: Optional[str]) -> bool:
    """Aulas especiais (gravação/manutenção) não disputam slot com transmissão ao vivo."""
    if tipo_a in TIPOS_ESPECIAIS and tipo_b == "Transmissão ao vivo":
        return False
    if tipo_a == "Transmissão ao vivo" and tipo_b in TIPOS_ESPECIAIS:
        return False
    return True


def _verificar_choque_horario(
    db: Session, data_aula: date, estudio: str, start: time, end: time,
    exclude_id: Optional[UUID] = None, canal_utilizado: Optional[str] = None,
    is_gravacao: bool = False, turma_id: Optional[UUID] = None,
    tipo_aula: Optional[str] = None,
) -> None:
    if not estudio:
        return
    # Sem canal IPTV ("N/A", vazio): só o estúdio conta. Senão todas as aulas sem canal no
    # mesmo horário (transmissão só pelo YouTube, gravação) seriam vistas como choque de canal.
    if (canal_utilizado or "").strip().upper() in ("", "N/A", "NA", "-", "—", "PENDENTE"):
        canal_utilizado = None
    mesmo_recurso = [ClassReport.estudio == estudio]
    if canal_utilizado:
        mesmo_recurso.append(ClassReport.canal_utilizado == canal_utilizado)

    conflitos_estudio: list = []
    conflitos_canal: list = []
    conflitos_turma: list = []

    # Para GRAVAÇÃO: verifica estudio OU canal no dia (OR lógico — ambos são recursos exclusivos)
    if is_gravacao:
        query = db.query(ClassReport).filter(
            ClassReport.data_aula == data_aula,
            ClassReport.is_deleted == False,
            ClassReport.status.in_(STATUS_FINALIZADOS),
            or_(*mesmo_recurso),
        )
        if exclude_id:
            query = query.filter(ClassReport.id != exclude_id)
        conflitos = query.all()

    # Para AULAS: verifica estudio + canal + intersecção real de horário
    else:
        if not start or not end:
            return

        filtros_base = [
            ClassReport.data_aula == data_aula,
            ClassReport.is_deleted == False,
            ClassReport.status.in_(STATUS_FINALIZADOS),
            ClassReport.start_time.isnot(None),
            ClassReport.end_time.isnot(None),
            ClassReport.start_time < end,
            ClassReport.end_time > start,
        ]

        # Choque de estúdio
        query_estudio = db.query(ClassReport).filter(
            *filtros_base,
            ClassReport.estudio == estudio,
        )
        if exclude_id:
            query_estudio = query_estudio.filter(ClassReport.id != exclude_id)
        conflitos_estudio = query_estudio.all()

        # Choque de canal (em estúdio diferente)
        conflitos_canal = []
        if canal_utilizado:
            query_canal = db.query(ClassReport).filter(
                *filtros_base,
                ClassReport.canal_utilizado == canal_utilizado,
                ClassReport.estudio != estudio,
            )
            if exclude_id:
                query_canal = query_canal.filter(ClassReport.id != exclude_id)
            conflitos_canal = query_canal.all()

        # Choque de turma — mesma turma + (mesmo estúdio OU mesmo canal) + horário sobreposto
        # Turma em estúdio E canal diferentes é operacionalmente válido (recursos físicos livres)
        conflitos_turma = []
        if turma_id:
            query_turma = db.query(ClassReport).filter(
                *filtros_base,
                ClassReport.turma_id == turma_id,
                or_(*mesmo_recurso),
            )
            if exclude_id:
                query_turma = query_turma.filter(ClassReport.id != exclude_id)
            conflitos_turma = query_turma.all()

        conflitos = conflitos_estudio + conflitos_canal + conflitos_turma

    conflitos = [
        c for c in conflitos
        if _tipos_competem_choque(tipo_aula, c.tipo_aula)
    ]

    if not conflitos:
        return

    if is_gravacao:
        tipo_choque = f"Estúdio ({estudio}) ou Canal ({canal_utilizado}) já estão em uso nesta data"
    elif not is_gravacao and conflitos_turma:
        tipo_choque = "A turma já possui outra aula no mesmo horário"
    elif not is_gravacao and conflitos_estudio and conflitos_canal:
        tipo_choque = f"Estúdio ({estudio}) e Canal ({canal_utilizado}) estão ocupados"
    elif not is_gravacao and conflitos_estudio:
        tipo_choque = f"Estúdio ({estudio}) já está ocupado"
    elif not is_gravacao and conflitos_canal:
        tipo_choque = f"Canal ({canal_utilizado}) já está sendo usado em outro estúdio"
    else:
        tipo_choque = f"Estúdio ({estudio}) e Canal ({canal_utilizado}) já estão em uso nesta data"

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=_formatar_mensagem_choque_horario(
            conflitos,
            f"⚠️ Choque de horário detectado! {tipo_choque}.",
        ),
    )


# ─── Validação Relacional Professor ↔ Disciplina ────────────────────


def _validar_professor_disciplina(
    db: Session, professor_id: UUID, disciplina_id: UUID
) -> None:
    """
    Compliance Crítico: Verifica se o professor está vinculado à disciplina.
    Apenas professores cadastrados para aquela disciplina podem ser selecionados.
    """
    vinculo = (
        db.query(ProfessorDisciplina)
        .filter(
            ProfessorDisciplina.professor_id == professor_id,
            ProfessorDisciplina.disciplina_id == disciplina_id,
        )
        .first()
    )

    if not vinculo:
        professor = db.query(Professor).filter(Professor.id == professor_id).first()
        disciplina = (
            db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
        )
        prof_nome = professor.nome if professor else str(professor_id)
        disc_nome = disciplina.nome if disciplina else str(disciplina_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Validação Relacional: Professor '{prof_nome}' não está "
                f"vinculado à disciplina '{disc_nome}'."
            ),
        )

def _obter_slots_grade_no_horario(
    db: Session,
    turma_id: UUID,
    data_aula: date,
    horario_aula: str,
    start_time=None
) -> list:
    import re
    if not turma_id or not data_aula:
        return []
    # v4: só os slots da grade que vale na data (versão ativa), igual à Agenda
    slots = slots_da_turma_no_dia(db, turma_id, data_aula)

    slots_no_horario = []
    if start_time:
        for s in slots:
            if s.horario_inicio and abs(
                (s.horario_inicio.hour * 60 + s.horario_inicio.minute) -
                (start_time.hour * 60 + start_time.minute)
            ) <= 5:
                slots_no_horario.append(s)
    else:
        def normalize_to_digits(s: str) -> str:
            if not s:
                return ""
            return re.sub(r"\D", "", s)
        norm_h = normalize_to_digits(horario_aula)
        for s in slots:
            is_gravacao = (s.horario_inicio.strftime("%H:%M") == "00:00") if s.horario_inicio else False
            if is_gravacao:
                horario_label = "GRAVAÇÃO"
            else:
                h_ini = s.horario_inicio.strftime("%H:%M") if s.horario_inicio else ""
                h_fim = s.horario_fim.strftime("%H:%M") if s.horario_fim else ""
                horario_label = f"{h_ini} às {h_fim}"
            if normalize_to_digits(horario_label) == norm_h:
                slots_no_horario.append(s)
    return slots_no_horario


# ─── v4: campos que o cliente não decide sozinho ──────────────────────
# slide_link é preenchido pela busca no Drive. O formulário do assistente não
# envia esse campo; antes, cada edição gravava None por cima e o PDF "sumia"
# (a coordenação não conseguia validar e a busca não rodava de novo).
CAMPOS_DO_COMPLIANCE = ("slide_link",)


def _aplicar_campos_do_payload(report: ClassReport, payload: dict, usuario: User) -> None:
    coordenacao = politicas.pode(usuario, "relatorio_aula.validar")
    for key, value in payload.items():
        if key in CAMPOS_DO_COMPLIANCE:
            # só a coordenação corrige à mão, e nunca apaga com vazio
            if not coordenacao or not (value or "").strip():
                continue
        setattr(report, key, value)


def _conferir_pedido_seduc(db: Session, report: ClassReport, valor_anterior: Optional[str],
                           usuario: Optional[User] = None) -> None:
    """
    v4: o pedido SEDUC (cobra gravação + exibição) é marcado pelo diretor-chefe na
    Agenda. A tela já trava o campo; aqui a API confere também, para o assistente.
    - Só vale para marcação nova (relatórios antigos com SEDUC ficam como estão).
    - Coordenação/admin podem marcar à mão (fica no histórico de versões).
    - Aceita agendamento SEDUC da turma ou sem turma na data da aula/gravação.
    """
    if (report.solicitante_antecipacao or "").upper() != "SEDUC" or (valor_anterior or "").upper() == "SEDUC":
        return
    if usuario is not None and politicas.pode(usuario, "relatorio_aula.validar"):
        return
    from app.models.agenda_estudio import AgendamentoEstudio

    datas = {d for d in (report.data_aula, report.data_execucao_real, report.data_referencia_aula) if d}
    q = db.query(AgendamentoEstudio).filter(
        or_(AgendamentoEstudio.turma_id == report.turma_id, AgendamentoEstudio.turma_id.is_(None)),
        AgendamentoEstudio.solicitante_antecipacao == "SEDUC",
        AgendamentoEstudio.status != "CANCELADO",
        or_(AgendamentoEstudio.data.in_(datas), AgendamentoEstudio.data_referencia.in_(datas)),
    )
    if not q.first():
        raise HTTPException(
            status_code=400,
            detail="Pedido SEDUC só vale quando o diretor-chefe marca na Agenda. "
                   "Peça para marcar a gravação como pedido SEDUC na Agenda e salve de novo.",
        )


# ─── v4: proteção contra relatório duplicado (restaurada) ─────────────
# Estas regras foram criadas em 19–21/08/2026 (commits 1b680d5, e503edf,
# ae09e89, bc7b323, 833b4be, 919ac31) e se perderam no merge "hml → prd" de
# 01/09/2026. Os testes delas (tests/test_ficheiro_duplicado.py e
# tests/test_report_slot_duplicity.py) continuaram no repositório e falhavam
# desde então. Duplicata de relatório vira cobrança em dobro.

def _is_gravacao_estudio(tipo_aula: Optional[str]) -> bool:
    return (tipo_aula or "").strip() == "Gravação estúdio"


def _is_transmissao_ao_vivo(tipo_aula: Optional[str]) -> bool:
    return (tipo_aula or "").strip() == "Transmissão ao vivo"


def _tipos_competem_slot(tipo_a: Optional[str], tipo_b: Optional[str]) -> bool:
    """Gravação estúdio e Transmissão ao vivo podem coexistir no mesmo slot."""
    if _is_gravacao_estudio(tipo_a) and _is_transmissao_ao_vivo(tipo_b):
        return False
    if _is_transmissao_ao_vivo(tipo_a) and _is_gravacao_estudio(tipo_b):
        return False
    return True


def _normalizar_chave_horario(horario_aula: Optional[str]) -> str:
    """Chave canônica para comparar horários (GRAVAÇÃO, 07:30 às 08:30, 07:30-08:30)."""
    if not horario_aula:
        return ""
    raw = horario_aula.strip()
    if raw.upper() in ("GRAVAÇÃO", "GRAVACAO", "GRAVACÃO"):
        return "GRAVACAO"
    digits = re.sub(r"\D", "", raw)
    if digits in ("", "0", "00", "000", "0000"):
        return "GRAVACAO"
    return digits


def _formatar_horario_canonico(horario_aula: Optional[str]) -> Optional[str]:
    """Normaliza o texto do horário antes de gravar (\"07:30-08:30\" → \"07:30 às 08:30\")."""
    if not horario_aula:
        return horario_aula
    if re.search(r"(?i)hor[áa]rio", horario_aula):  # "1º Horário" fica como está (resolvido depois)
        return horario_aula.strip()
    chave = _normalizar_chave_horario(horario_aula)
    if chave == "GRAVACAO":
        return "GRAVAÇÃO"
    if len(chave) >= 8:
        return f"{chave[0:2]}:{chave[2:4]} às {chave[4:6]}:{chave[6:8]}"
    if len(chave) == 4:
        return f"{chave[0:2]}:{chave[2:4]}"
    return horario_aula.strip()


def _query_relatorios_ativos_slot(
    db: Session,
    turma_id: UUID,
    data_aula: date,
    disciplina_id: UUID,
    exclude_report_id: Optional[UUID] = None,
    only_finalizados: bool = False,
):
    query = db.query(ClassReport).filter(
        ClassReport.turma_id == turma_id,
        ClassReport.data_aula == data_aula,
        ClassReport.disciplina_id == disciplina_id,
        ClassReport.is_deleted == False,  # noqa: E712
        ClassReport.status != "CANCELADO",
    )
    if only_finalizados:
        query = query.filter(ClassReport.status.in_(STATUS_FINALIZADOS))
    if exclude_report_id:
        query = query.filter(ClassReport.id != exclude_report_id)
    return query.all()


def _validar_slot_unico(
    db: Session,
    turma_id: UUID,
    data_aula: date,
    horario_aula: str,
    disciplina_id: UUID,
    exclude_report_id: Optional[UUID] = None,
    only_finalizados: bool = False,
    tipo_aula: Optional[str] = None,
) -> None:
    """Um único registro ativo por turma + data + horário + disciplina (tipos compatíveis)."""
    if not turma_id or not data_aula or not horario_aula or not disciplina_id:
        return
    chave_alvo = _normalizar_chave_horario(horario_aula)
    for r in _query_relatorios_ativos_slot(
        db, turma_id, data_aula, disciplina_id, exclude_report_id, only_finalizados
    ):
        if _normalizar_chave_horario(r.horario_aula) != chave_alvo:
            continue
        if not _tipos_competem_slot(tipo_aula, r.tipo_aula):
            continue
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_formatar_mensagem_choque_horario(
                [r],
                "⚠️ Choque de horário detectado! Já existe um registro para este slot operacional.",
            ),
        )


def _gerar_nome_ficheiro(turma, disciplina, data_aula, conteudo) -> Optional[str]:
    if not turma or not data_aula or not conteudo:
        return None
    try:
        return gerar_nome_padronizado(
            nomenclatura_turma=turma.nomenclatura_padrao or turma.nome,
            disciplina=disciplina.nome if disciplina else "",
            data_aula=data_aula,
            conteudo=conteudo,
            modalidade=turma.modalidade,
        )
    except ValueError:
        return None


def _validar_ficheiro_duplicado(
    db: Session,
    data_aula: date,
    nome_ficheiro: Optional[str],
    exclude_report_id: Optional[UUID] = None,
) -> None:
    """
    Impede dois relatórios FINALIZADOS (fila ou validados) com o mesmo arquivo na
    mesma data. Rascunhos podem coexistir; a trava vale na finalização.
    """
    nome_alvo = normalizar_para_match(nome_ficheiro or "")
    if not data_aula or not nome_alvo:
        return
    query = db.query(ClassReport).filter(
        ClassReport.data_aula == data_aula,
        ClassReport.is_deleted == False,  # noqa: E712
        ClassReport.status.in_(STATUS_FINALIZADOS),
    )
    if exclude_report_id:
        query = query.filter(ClassReport.id != exclude_report_id)
    for r in query.all():
        nome_existente = r.nome_ficheiro_gerado
        if not nome_existente:
            turma_r = db.query(Turma).filter(Turma.id == r.turma_id).first()
            disc_r = db.query(Disciplina).filter(Disciplina.id == r.disciplina_id).first()
            nome_existente = _gerar_nome_ficheiro(turma_r, disc_r, r.data_aula, r.conteudo_ministrado or "")
        if normalizar_para_match(nome_existente or "") == nome_alvo:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Já existe um registro com o mesmo ficheiro nesta data ({data_aula.strftime('%d/%m/%Y')}). "
                    f"Status atual: {r.status}. Ficheiro: {nome_ficheiro}. "
                    "Altere o conteúdo ministrado para diferenciar o registro."
                ),
            )


def _validar_duplicidade_limite_slot(
    db: Session,
    turma_id: UUID,
    data_aula: date,
    horario_aula: str,
    regular: str,
    start_time,
    exclude_report_id: Optional[UUID] = None,
    tipo_aula: Optional[str] = None,
    only_finalizados: bool = False,
) -> None:
    # Apenas valida slots duplicados para aulas REGULARES.
    # Gravações e Aulas Avulsas (regular != "Sim") não possuem slot fixo e são livres.
    if regular != "Sim" or not turma_id or not data_aula or not horario_aula:
        return

    # Se o próprio registro for de gravação ou manutenção especial, pula a validação
    if tipo_aula in TIPOS_ESPECIAIS:
        return

    # 1. Busca todos os relatórios não excluídos cadastrados para a mesma data e horário
    # Excluindo registros do tipo gravação ou manutenção especial
    query = db.query(ClassReport).filter(
        ClassReport.turma_id == turma_id,
        ClassReport.data_aula == data_aula,
        ClassReport.horario_aula == horario_aula,
        ClassReport.is_deleted == False,
        ClassReport.tipo_aula.notin_(list(TIPOS_ESPECIAIS))
    )
    if only_finalizados:
        query = query.filter(ClassReport.status.in_(STATUS_FINALIZADOS))
    if exclude_report_id:
        query = query.filter(ClassReport.id != exclude_report_id)
    existing_reports = query.all()
    
    # 2. Obtém o número de slots configurados na grade oficial
    slots = _obter_slots_grade_no_horario(db, turma_id, data_aula, horario_aula, start_time)
    limite = max(1, len(slots))
    
    # 3. Se atingiu ou passou o limite, bloqueia a gravação
    if len(existing_reports) >= limite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_formatar_mensagem_choque_horario(
                existing_reports,
                "⚠️ Choque de horário detectado! O slot já está ocupado.",
            ),
        )


# ─── Validação de Slot da Grade Horária ─────────────────────────

_DIAS_SEMANA_PT = {0: "SEGUNDA", 1: "TERÇA", 2: "QUARTA", 3: "QUINTA", 4: "SEXTA", 5: "SÁBADO", 6: "DOMINGO"}


def _validar_slot_grade(
    db: Session,
    turma_id: UUID,
    data_aula,
    disciplina_id: UUID,
    horario_aula: str,
    regular: str,
    start_time=None,
) -> None:
    """
    Para aulas regulares, verifica se a disciplina bate com o slot oficial da grade.
    Só bloqueia se existir um slot explícito com outra disciplina (não bloqueia quando grade está vazia).
    """
    if regular != "Sim" or not turma_id or not disciplina_id or not data_aula:
        return

    dia_num = data_aula.weekday()  # 0=Segunda … 6=Domingo (int, mesmo tipo da coluna)
    dia_nome = _DIAS_SEMANA_PT.get(dia_num, "")
    if not dia_nome:
        return

    # v4: só os slots da grade que vale na data (versão ativa), igual à Agenda
    slots = slots_da_turma_no_dia(db, turma_id, data_aula)

    if not slots:
        return

    # Tenta encontrar todos os slots que batem com o horário resolvido
    slots_no_horario = []
    if start_time:
        for s in slots:
            if s.horario_inicio and abs(
                (s.horario_inicio.hour * 60 + s.horario_inicio.minute) -
                (start_time.hour * 60 + start_time.minute)
            ) <= 5:
                slots_no_horario.append(s)

    slot_match = None
    if slots_no_horario:
        # 1. Tenta encontrar slot com a mesma disciplina
        for s in slots_no_horario:
            if s.disciplina_id == disciplina_id:
                slot_match = s
                break
        
        # 2. Se não encontrou, tenta encontrar um slot sem disciplina definida (None)
        if not slot_match:
            for s in slots_no_horario:
                if s.disciplina_id is None:
                    slot_match = s
                    break

        # 3. Se ainda assim não encontrou, levanta erro informando as disciplinas esperadas
        if not slot_match:
            nomes_previstos = []
            for s in slots_no_horario:
                if s.disciplina:
                    nomes_previstos.append(f"'{s.disciplina.nome}'")
                elif s.disciplina_id:
                    nomes_previstos.append(f"'{s.disciplina_id}'")
            
            # Remove duplicados mantendo a ordem original
            nomes_unicos = []
            for n in nomes_previstos:
                if n not in nomes_unicos:
                    nomes_unicos.append(n)
                    
            slot_disc_nome = " ou ".join(nomes_unicos) if nomes_unicos else "outra disciplina"
            disc_obj = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
            disc_nome = disc_obj.nome if disc_obj else str(disciplina_id)
            raise HTTPException(
                status_code=400,
                detail=f"Esse horário regular deveria ser de {slot_disc_nome}. "
                       f"Registrar '{disc_nome}' aqui substituiria indevidamente a grade. "
                       f"Se for substituição oficial, marque 'Aula Regular = Não'.",
            )
    else:
        # Sem match por horário — tenta match por disciplina (permissivo)
        matched_by_disc = [s for s in slots if s.disciplina_id == disciplina_id]
        if matched_by_disc:
            return  # disciplina está na grade para este dia, ok

        # Há slots para este dia mas nenhum bate com esta disciplina — alerta apenas se todos tiverem disciplina definida
        slots_com_disc = [s for s in slots if s.disciplina_id is not None]
        if not slots_com_disc:
            return  # grade sem disciplinas definidas, não bloqueia

        disc_obj = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
        disc_nome = disc_obj.nome if disc_obj else str(disciplina_id)
        nomes_esperados = ", ".join(
            s.disciplina.nome for s in slots_com_disc[:3] if s.disciplina
        )
        raise HTTPException(
            status_code=400,
            detail=f"A disciplina '{disc_nome}' não está prevista na grade para {dia_nome.capitalize()}. "
                   f"Disciplinas previstas: {nomes_esperados}. "
                   f"Se for substituição, certifique-se de marcar 'Aula Regular = Não'.",
        )

    # Verificação adicional: Grade Base não permite mudança de horário
    if slot_match and slot_match.versao == "Grade Base" and horario_aula and start_time:
        if slot_match.horario_inicio and slot_match.horario_inicio != start_time:
            raise HTTPException(
                status_code=400,
                detail=f"Mudança de horário não permitida para disciplinas com horário fixo (Grade Base). "
                       f"Horário oficial: {slot_match.horario_inicio.strftime('%H:%M')}.",
            )


# ─── Módulo Auxiliar: Buscas Diretores ───────────────────────────

@router.get("/lookup/diretores")
def listar_diretores_dropdown(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Devolve a lista de Diretores de Imagem ATIVOS para popular Selects."""
    diretores = db.query(DiretorImagem).filter(DiretorImagem.is_active == True).order_by(DiretorImagem.nome).all()
    return [{"id": str(d.id), "nome": d.nome} for d in diretores]



@router.get("/lookup/disciplinas")
def listar_disciplinas(
    turma_id: Optional[UUID] = Query(None, description="Só as disciplinas da grade desta turma"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Disciplinas ATIVAS. Com `turma_id`, só as que estão na grade da turma:
    os slots da versão de grade ativa ou, se a turma não tiver versão ativa,
    os slots antigos sem versão. Turma sem disciplina na grade devolve lista vazia
    (o formulário então mostra todas).
    """
    q = db.query(Disciplina).filter(Disciplina.is_active == True)
    if turma_id:
        from app.models.infraestrutura import GradeVersao

        versao_ativa = (
            db.query(GradeVersao.id)
            .filter(GradeVersao.turma_id == turma_id, GradeVersao.is_active == True)
            .first()
        )
        slots = db.query(Grade.disciplina_id).filter(
            Grade.turma_id == turma_id, Grade.disciplina_id.isnot(None)
        )
        if versao_ativa:
            slots = slots.filter(Grade.grade_versao_id == versao_ativa[0])
        else:
            slots = slots.filter(Grade.grade_versao_id.is_(None))
        ids = {row[0] for row in slots.distinct().all()}
        if not ids:
            return []
        q = q.filter(Disciplina.id.in_(ids))
    disciplinas = q.order_by(Disciplina.nome).all()
    return [{"id": str(d.id), "nome": d.nome} for d in disciplinas]


@router.get("/lookup/professores")
def listar_professores(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Retorna todos os professores ATIVOS cadastrados."""
    professores = db.query(Professor).filter(Professor.is_active == True).order_by(Professor.nome).distinct(Professor.nome).all()
    return [{"id": str(p.id), "nome": p.nome} for p in professores]


@router.get("/lookup/users")
def listar_usuarios_dropdown(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Usuários para o filtro "Usuário" da Auditoria: apenas quem tem ao menos um
    relatório de aula lançado (contas sem relatórios só geravam opções vazias e
    nomes repetidos). Nomes iguais vêm com o e-mail para diferenciar.
    """
    com_relatorio = (
        db.query(ClassReport.created_by)
        .filter(ClassReport.is_deleted == False)  # noqa: E712
        .distinct()
    )
    usuarios = (
        db.query(User)
        .filter(User.id.in_(com_relatorio))
        .order_by(User.full_name)
        .all()
    )
    contagem_nomes: dict = {}
    for u in usuarios:
        chave = (u.full_name or "").strip().lower()
        contagem_nomes[chave] = contagem_nomes.get(chave, 0) + 1
    resultado = []
    for u in usuarios:
        nome = (u.full_name or u.email or "").strip()
        if contagem_nomes.get(nome.lower(), 0) > 1 and u.email:
            nome = f"{nome} ({u.email})"
        resultado.append({"id": str(u.id), "nome": nome})
    return resultado

@router.get("/lookup/bncc")
def lookup_bncc(
    current_user: User = Depends(get_current_active_user),
):
    """Retorna a lista de habilidades BNCC carregadas do arquivo JSON."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(base_dir, "data", "bncc.json")

    if not os.path.exists(json_path):
        import logging
        logging.getLogger(__name__).warning(f"BNCC JSON não encontrado em: {json_path}")
        return []

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Erro ao carregar BNCC: {e}")
        return []

# ─── Filtros e Regras Centralizadas ───────────────────────────────────────────────────


def _report_list_query_options(query):
    """Eager-load de relações usadas nos campos derivados da resposta."""
    return query.options(
        joinedload(ClassReport.creator),
        joinedload(ClassReport.turma),
        joinedload(ClassReport.disciplina),
        joinedload(ClassReport.professor),
        joinedload(ClassReport.diretor_imagem_rel),
        joinedload(ClassReport.validador),
    )


def _eh_exibicao_antecipada(report: ClassReport) -> bool:
    from app.services.image_director_associacao import PREFIXO_EXIBICAO

    return (getattr(report, "motivo_referencia", None) or "").startswith(PREFIXO_EXIBICAO)


def _professor_da_exibicao(report: ClassReport) -> None:
    """
    Reunião (out/2026): o professor é pago na GRAVAÇÃO. Na exibição de uma aula gravada
    antes (ligada na Agenda), o relatório vai sem professor para não pagar duas vezes.
    """
    if _eh_exibicao_antecipada(report):
        report.professor_id = None
        report.professor_nome_externo = None


def _aplicar_link_da_agenda(db: Session, report: ClassReport) -> None:
    """
    Link do YouTube da aula: vem do que o diretor-chefe cadastrou na Agenda para o estúdio
    e turno do dia (o mesmo do relatório do diretor). Quando cadastrado, vale no relatório.
    Reposição: vale o dia em que a aula foi gravada/transmitida.
    """
    try:
        from app.services.agenda_estudios import transmissao_do_estudio
        dia = getattr(report, "data_execucao_real", None) or report.data_aula
        tx = transmissao_do_estudio(db, dia, report.turno, report.estudio)
    except Exception:
        return
    if tx.get("youtube_link"):
        report.youtube_link = tx["youtube_link"]


def _apply_report_filters(query, db: Optional[Session] = None, **kwargs):
    """
    Aplica filtros ao query de relatórios (reutilizado em lista, auditoria,
    estatísticas e exportação). Com `db`, os filtros de estúdio, professor e
    disciplina consideram grafias/cadastros equivalentes.
    """
    from app.services.filtros import (
        disciplina_equivalentes,
        estudio_variantes,
        professor_equivalentes,
        validar_periodo,
    )

    validar_periodo(kwargs.get("data_inicio"), kwargs.get("data_fim"))

    # Sempre filtrar soft deleted
    query = query.filter(ClassReport.is_deleted == False)  # noqa: E712
    # Exportação/faturamento: a aula entra no período pela data da gravação, quando existe
    # (aula de 30/10 gravada em 03/11 vai para novembro). Nas telas vale a data da aula.
    col_data = (
        func.coalesce(ClassReport.data_execucao_real, ClassReport.data_aula)
        if kwargs.get("periodo_por_gravacao") else ClassReport.data_aula
    )
    if kwargs.get("data_aula"):
        query = query.filter(col_data == kwargs["data_aula"])
    if kwargs.get("data_inicio"):
        query = query.filter(col_data >= kwargs["data_inicio"])
    if kwargs.get("data_fim"):
        query = query.filter(col_data <= kwargs["data_fim"])
    if kwargs.get("turma_id"):
        query = query.filter(ClassReport.turma_id == kwargs["turma_id"])
    if kwargs.get("professor_id"):
        if db is not None:
            prof_ids, prof_nome = professor_equivalentes(db, kwargs["professor_id"])
            conds = [
                ClassReport.professor_id.in_(prof_ids),
                ClassReport.professor_substituto_id.in_(prof_ids),
            ]
            if prof_nome:
                from app.services.filtros import valores_equivalentes

                ext = valores_equivalentes(db, ClassReport.professor_nome_externo, prof_nome)
                sub = valores_equivalentes(db, ClassReport.professor_substituto_nome_externo, prof_nome)
                if ext:
                    conds.append(ClassReport.professor_nome_externo.in_(ext))
                if sub:
                    conds.append(ClassReport.professor_substituto_nome_externo.in_(sub))
            query = query.filter(or_(*conds))
        else:
            query = query.filter(ClassReport.professor_id == kwargs["professor_id"])
    if kwargs.get("disciplina_id"):
        if db is not None:
            disc_ids, _ = disciplina_equivalentes(db, kwargs["disciplina_id"])
            query = query.filter(ClassReport.disciplina_id.in_(disc_ids))
        else:
            query = query.filter(ClassReport.disciplina_id == kwargs["disciplina_id"])
    if kwargs.get("status_filter"):
        query = query.filter(ClassReport.status == kwargs["status_filter"].strip().upper())
    if kwargs.get("estudio"):
        if db is not None:
            query = query.filter(ClassReport.estudio.in_(estudio_variantes(db, ClassReport.estudio, kwargs["estudio"])))
        else:
            query = query.filter(ClassReport.estudio == kwargs["estudio"])
    if kwargs.get("tipo_aula"):
        query = query.filter(ClassReport.tipo_aula == kwargs["tipo_aula"])
    if kwargs.get("com_atraso") is True:
        query = query.filter(ClassReport.teve_atraso == True)  # noqa: E712
    if kwargs.get("com_substituicao") is True:
        query = query.filter(ClassReport.teve_substituicao == True)  # noqa: E712
    if kwargs.get("com_problema"):
        query = query.filter(
            ClassReport.problema_material.isnot(None),
            ClassReport.problema_material != "Não",
            ClassReport.problema_material != "",
        )
    if kwargs.get("created_by"):
        query = query.filter(ClassReport.created_by == kwargs["created_by"])
    if kwargs.get("precisa_correcao") is not None:
        query = query.filter(ClassReport.precisa_correcao == kwargs["precisa_correcao"])
    if kwargs.get("modalidade_aula"):
        query = query.filter(filtro_modalidade_class_report(kwargs["modalidade_aula"]))
    if kwargs.get("status_idr"):
        query = query.filter(filtro_status_idr_class_report(kwargs["status_idr"]))
    fila = (kwargs.get("fila_validacao") or "").strip().lower()
    if fila in ("prontos", "aguardando"):
        # Fila da coordenação: só valida quando os dois links (vídeo e PDF) já foram coletados
        com_links = and_(
            func.coalesce(func.trim(ClassReport.video_link), "") != "",
            func.coalesce(func.trim(ClassReport.slide_link), "") != "",
        )
        query = query.filter(ClassReport.status == "AGUARDANDO_VALIDACAO")
        query = query.filter(com_links if fila == "prontos" else not_(com_links))
    return query


MODALIDADES_AULA = ("gravacao", "transmissao")


def _validar_modalidade(modalidade: str) -> str:
    m = (modalidade or "").strip().lower()
    if m not in MODALIDADES_AULA:
        raise HTTPException(status_code=422, detail="Filtro Gravação/Transmissão inválido.")
    return m


def filtro_modalidade_class_report(modalidade: str):
    """Gravação = 'Gravação estúdio' / 'Gravação externa'; Transmissão = 'Transmissão ao vivo'."""
    m = _validar_modalidade(modalidade)
    if m == "gravacao":
        return func.lower(ClassReport.tipo_aula).like("grava%")
    return func.lower(ClassReport.tipo_aula).like("transmiss%")


STATUS_IDR_VALIDOS = ("RASCUNHO", "AGUARDANDO_VALIDACAO", "VALIDADO", "CANCELADO", "FINALIZADO", "SEM_RELATORIO")


def filtro_status_idr_class_report(status_idr: str):
    """
    Status do relatório do Diretor de Imagem vinculado ao relatório de aula
    (vínculo direto no cabeçalho ou em alguma aula do relatório do diretor).
    'SEM_RELATORIO' = aula sem relatório do diretor vinculado.
    """
    from app.models.image_director_report import ImageDirectorLesson, ImageDirectorReport

    st = (status_idr or "").strip().upper()
    if st not in STATUS_IDR_VALIDOS:
        raise HTTPException(status_code=422, detail="Filtro de status do Diretor de Imagem inválido.")

    from sqlalchemy import select

    base_cab = select(ImageDirectorReport.class_report_id).where(
        ImageDirectorReport.is_deleted == False,  # noqa: E712
        ImageDirectorReport.class_report_id.isnot(None),
    )
    base_aula = (
        select(ImageDirectorLesson.class_report_id)
        .join(ImageDirectorReport, ImageDirectorLesson.report_id == ImageDirectorReport.id)
        .where(
            ImageDirectorReport.is_deleted == False,  # noqa: E712
            ImageDirectorLesson.class_report_id.isnot(None),
        )
    )
    if st == "SEM_RELATORIO":
        return and_(~ClassReport.id.in_(base_cab), ~ClassReport.id.in_(base_aula))
    return or_(
        ClassReport.id.in_(base_cab.where(ImageDirectorReport.status == st)),
        ClassReport.id.in_(base_aula.where(ImageDirectorReport.status == st)),
    )

# ─── Helper: WebSocket Broadcast após mutação de relatório (TASK 06) ──────

def _broadcast_report_update(action: str, report_id: str, user_name: str = ""):
    """
    Dispara broadcast WebSocket para notificar Live Monitor e Grade de mudanças.

    v4: as rotas de relatório são síncronas (rodam numa thread do FastAPI, sem
    event loop). Antes, asyncio.get_event_loop() falhava ali e o aviso nunca saía.
    Agora o envio é entregue ao loop principal com anyio.from_thread.
    Limite conhecido: com mais de um processo (gunicorn workers) cada processo só
    avisa as conexões abertas nele.
    """
    mensagem = {
        "type": "REPORT_UPDATED",
        "action": action,
        "report_id": report_id,
        "updated_by": user_name,
    }
    try:
        from app.api.websocket.connection_manager import manager
        import anyio.from_thread

        try:
            anyio.from_thread.run(manager.broadcast, mensagem)
            return
        except RuntimeError:
            pass  # não está numa thread do anyio (ex.: chamada direta em teste/script)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(manager.broadcast(mensagem))
        except RuntimeError:
            asyncio.run(manager.broadcast(mensagem))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"WebSocket broadcast failed: {e}")

@router.get("/drive-suggestions")
def sugestoes_drive(
    data_aula: date,
    turma_id: UUID,
    disciplina_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Busca no Google Drive arquivos de vídeo gravados no dia que dão match com a Turma e Disciplina,
    devolvendo apenas a parte final do nome (o Conteúdo Ministrado) para sugestão no Frontend.
    """
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    disciplina = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()

    if not turma or not disciplina:
        return {"suggestions": []}

    from app.services.naming_engine import gerar_nome_padronizado
    import re
    from app.services.sync_drive import get_drive_service

    # Para TECNICO o front-end envia no conteúdo "AULA NN DISCIPLINA"
    dummy_name = gerar_nome_padronizado(
        nomenclatura_turma=turma.nomenclatura_padrao or turma.nome,
        disciplina=disciplina.nome,
        data_aula=data_aula,
        conteudo="AULA 00 " + disciplina.nome + " DUMMY CONTENT",
        modalidade=turma.modalidade,
    )

    prefixo = dummy_name.replace("DUMMY CONTENT 12345.mp4", "").strip()

    service = get_drive_service()
    if not service:
        return {"suggestions": []}

    match_data = re.search(r'(\d{2})\s(\d{2})\s(\d{2})', prefixo)
    if not match_data:
        return {"suggestions": []}

    dia, mes, ano = match_data.groups()
    query_data = f"name contains '{dia}' and name contains '{mes}' and name contains '{ano}' and mimeType contains 'video' and trashed = false"

    expected_class_disc = prefixo.replace(f"{dia} {mes} {ano}", "").strip()
    from app.services.sync_drive import normalize_for_search
    expected_class_disc_norm = normalize_for_search(expected_class_disc)
    import difflib

    try:
        results = service.files().list(
            q=query_data,
            fields="files(id, name)",
            pageSize=50,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives"
        ).execute()

        items = results.get('files', [])
        sugestoes = set()

        for file in items:
            name = file.get('name', '')
            name_no_ext = re.sub(r'(?i)\.mp4$', '', name).strip()
            drive_norm = normalize_for_search(name_no_ext)

            if dia in name_no_ext and mes in name_no_ext and ano in name_no_ext:
                ratio = max(
                    difflib.SequenceMatcher(None, expected_class_disc_norm, drive_norm[:len(expected_class_disc_norm)]).ratio(),
                    difflib.SequenceMatcher(None, expected_class_disc_norm, drive_norm[:len(expected_class_disc_norm) + 5]).ratio()
                )

                if ratio > 0.65:
                    m_orig = re.search(r'\d{2}[^\d]*\d{2}[^\d]*\d{2}[^\w]*(.*)', name_no_ext)
                    if m_orig:
                        conteudo_final = m_orig.group(1).strip()
                        if conteudo_final:
                            sugestoes.add(conteudo_final.upper())
                        else:
                            sugestoes.add(name_no_ext.upper())
                    else:
                        sugestoes.add(name_no_ext.upper())

        return {"suggestions": list(sugestoes)[:5]}
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Erro ao buscar sugestões no Drive: {e}")
        return {"suggestions": []}


# ─── CRUD ─────────────────────────────────────────────────────────────


@router.post("/", response_model=ClassReportResponse, status_code=status.HTTP_201_CREATED, dependencies=_WRITE_DEPS)
def criar_relatorio(
    data: ClassReportCreate,
    bypass_clash: bool = Query(False, description="Forçar registro mesmo com conflito (Admin)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Cria um novo relatório de aula (status RASCUNHO).
    Auto-preenche os metadados e valida campos condicionais.
    """
    politicas.exigir(current_user, "relatorio_aula.criar")
    try:
        # 1. Validação das entidades referenciadas
        turma = db.query(Turma).filter(Turma.id == data.turma_id).first()
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada.")

        if data.professor_id:
            professor = db.query(Professor).filter(Professor.id == data.professor_id).first()
            if not professor:
                raise HTTPException(status_code=404, detail="Professor não encontrado.")

            # 2. Validação relacional Professor ↔ Disciplina
            _validar_professor_disciplina(db, data.professor_id, data.disciplina_id)

        # 3. Validação de campos condicionais
        _validar_campos_condicionais(data)

        # 4. Verificar duplicidade (Permite múltiplas disciplinas no mesmo horário para a mesma turma)
        # Ignora e exclui gravações/manutenções especiais
        # v4 (restaurado de 19/08): horário em formato único, mesmo arquivo na mesma
        # data e um relatório por slot (horário "07:30-08:30" = "07:30 às 08:30").
        if data.horario_aula:
            data.horario_aula = _formatar_horario_canonico(data.horario_aula)
        disciplina_nova = db.query(Disciplina).filter(Disciplina.id == data.disciplina_id).first()
        nome_previsto = _gerar_nome_ficheiro(turma, disciplina_nova, data.data_aula, data.conteudo_ministrado)
        if nome_previsto:
            _validar_ficheiro_duplicado(db, data.data_aula, nome_previsto)
        _validar_slot_unico(
            db, data.turma_id, data.data_aula, data.horario_aula, data.disciplina_id,
            tipo_aula=data.tipo_aula,
        )

        # 4. Tentar extrair horários se for regular e não vier preenchido
        start_t = data.start_time
        end_t = data.end_time
        if data.regular == "Sim" and not start_t:
            nomenclatura = turma.nomenclatura_padrao if turma else ""
            start_t, end_t = _resolver_horario(
                data.horario_aula,
                nomenclatura,
                turno_usuario=data.turno or ""
            )
            if start_t and end_t:
                data.start_time = start_t
                data.end_time = end_t

        # Verificar se o slot de horário excede o limite de relatórios permitidos
        _validar_duplicidade_limite_slot(
            db=db,
            turma_id=data.turma_id,
            data_aula=data.data_aula,
            horario_aula=data.horario_aula,
            regular=data.regular,
            start_time=data.start_time,
            exclude_report_id=None,
            tipo_aula=data.tipo_aula
        )

        # 5. Validações de grade e choque de horário foram movidas para 'finalizar_relatorio' (Permite salvar rascunho sem travar)

        # 6. Criação do relatório
        dados_novos = data.model_dump()
        if not politicas.pode(current_user, "relatorio_aula.validar"):
            for campo in CAMPOS_DO_COMPLIANCE:
                dados_novos.pop(campo, None)
        report = ClassReport(
            created_by=current_user.id,
            status="RASCUNHO",
            **dados_novos,
        )
        _conferir_pedido_seduc(db, report, None, current_user)

        # Data da gravação × data da aula na grade (reposição / antecipada) e o indicativo
        ajustar_datas_gravacao(report)
        _professor_da_exibicao(report)
        _aplicar_link_da_agenda(db, report)

        db.add(report)
        db.flush()
        vincular_image_director_ao_class_report(db, report)
        registrar_versao(db, TIPO_AULA, report, "CRIADO", current_user)
        if current_user.role == "admin":
            log = AuditLog(
                actor_id=current_user.id,
                action="CREATE_REPORT",
                details=f"Admin criou o relatório {report.id}"
            )
            db.add(log)
        db.commit()
        db.refresh(report)

        # TASK 06: Broadcast WebSocket
        _broadcast_report_update("CREATED", str(report.id), current_user.full_name)

        return report

    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as ie:
        db.rollback()
        if "uq_class_report_turma_data_horario" in str(ie.orig):
            raise HTTPException(
                status_code=409,
                detail="Não foi possível salvar o relatório. Já existe um relatório ativo (ou rascunho) registrado para esta Turma, Data, Horário e Disciplina.",
            )
        raise HTTPException(status_code=400, detail="Erro de integridade ao salvar registro.")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Erro Crítico em criar_relatorio: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro interno ao criar o relatório. Os dados não foram salvos; tente de novo e, se continuar, avise o suporte.")


@router.patch("/{report_id}/finalizar", response_model=ClassReportResponse, dependencies=_WRITE_DEPS)
@router.post("/{report_id}/finalizar", response_model=ClassReportResponse, dependencies=_WRITE_DEPS)
@router.post("/{report_id}/finalize", response_model=ClassReportResponse, dependencies=_WRITE_DEPS)
def finalizar_relatorio(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Finaliza o relatório: executa o Naming Engine, verifica aulas geminadas (P1/P2/P3)
    e envia para a fila de validação da Coordenação (status = AGUARDANDO_VALIDACAO).
    """
    # ✅ Soft delete: ignora relatórios arquivados
    report = db.query(ClassReport).filter(
        ClassReport.id == report_id,
        ClassReport.is_deleted == False,  # noqa: E712
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")

    # v4: dono e status são conferidos antes de qualquer outra coisa
    politicas.exigir(current_user, "relatorio_aula.finalizar", autor_id=report.created_by)
    status_anterior = report.status
    novo_status = estados.destino("finalizar", report.status)

    # --- TASK 09: Validação Rígida na Finalização ---
    if report.interacao_professor_aluno == "Outras" and not report.interacao_outras_desc:
        raise HTTPException(status_code=400, detail="Justificativa de interação 'Outras' obrigatória.")

    if report.teve_substituicao and not report.professor_substituto_id and not report.professor_substituto_nome_externo:
        raise HTTPException(status_code=400, detail="Professor substituto obrigatório para aulas com substituição.")

    if report.teve_atraso:
        if not report.minutos_atraso or report.minutos_atraso == "00:00":
            raise HTTPException(status_code=400, detail="Tempo de atraso é obrigatório para aulas com atraso.")
        if not report.observacao_atraso:
            raise HTTPException(status_code=400, detail="Justificativa do atraso é obrigatória.")

    if report.regular == "Não" and not report.ticket_number:
        raise HTTPException(status_code=400, detail="Ticket Number é obrigatório para aulas avulsas.")

    if report.problema_material == "Sim" and not report.problematic_materials:
        raise HTTPException(
            status_code=400,
            detail="É obrigatório descrever os materiais problemáticos para finalizar o relatório."
        )

    # Link do YouTube: o que o diretor-chefe cadastrou na Agenda para o estúdio e turno
    _aplicar_link_da_agenda(db, report)

    # Bloquear finalização se faltar URL do Youtube (TASK 30)
    if not report.youtube_link:
        raise HTTPException(
            status_code=400,
            detail="Não é possível finalizar o relatório: o 'Link do YouTube' é obrigatório. "
                   "Ele vem do que o diretor-chefe cadastra na Agenda (Link e chave do dia) para o estúdio e turno.",
        )

    is_avulsa = report.regular == "Não"
    is_especial = report.tipo_aula in TIPOS_ESPECIAIS
    _professor_da_exibicao(report)
    if not is_avulsa and not is_especial and not _eh_exibicao_antecipada(report):
        if not report.professor_id:
            from app.utils.text_utils import is_placeholder_professor

            ext = (report.professor_nome_externo or "").strip()
            if not ext or is_placeholder_professor(ext):
                raise HTTPException(
                    status_code=400,
                    detail="Informe o professor antes de finalizar o relatório.",
                )

    # Buscar turma para dados do naming engine
    turma = db.query(Turma).filter(Turma.id == report.turma_id).first()
    disciplina = (
        db.query(Disciplina).filter(Disciplina.id == report.disciplina_id).first()
    )

    # Gerar nome padronizado via Naming Engine
    # v4: conteúdo fora do padrão (ex.: TÉCNICO sem "AULA NN") vira 400 com a
    # explicação, em vez de erro 500.
    try:
        nome_gerado = gerar_nome_padronizado(
            nomenclatura_turma=turma.nomenclatura_padrao or turma.nome,
            disciplina=disciplina.nome if disciplina else "",
            data_aula=report.data_aula,
            conteudo=report.conteudo_ministrado,
            modalidade=turma.modalidade,
        )
    except ValueError as erro_nome:
        raise HTTPException(status_code=400, detail=str(erro_nome))

    # Verificação de aulas geminadas (P1/P2/P3) - Ignorar completamente para modalidade TECNICO
    # ou se for gravação/manutenção especial
    is_tecnico = (turma.modalidade.strip().upper() == "TECNICO") if (turma and turma.modalidade) else False
    is_especial = report.tipo_aula in TIPOS_ESPECIAIS

    if not is_tecnico and not is_especial:
        aulas_existentes = (
            db.query(ClassReport)
            .filter(
                ClassReport.turma_id == report.turma_id,
                ClassReport.disciplina_id == report.disciplina_id,
                ClassReport.data_aula == report.data_aula,
                ClassReport.status.in_(STATUS_FINALIZADOS),
                ClassReport.is_deleted == False,  # noqa: E712
                ClassReport.id != report.id,
                ClassReport.tipo_aula.notin_(list(TIPOS_ESPECIAIS))
            )
            .all()
        )

        if aulas_existentes:
            # 1) Mesmo horário: não é geminada, é o MESMO relatório lançado de novo
            mesma_aula = next((a for a in aulas_existentes if _mesmo_horario(a, report)), None)
            if mesma_aula:
                quem = mesma_aula.creator.full_name if getattr(mesma_aula, "creator", None) else "outro usuário"
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Esta aula ({report.horario_aula or 'mesmo horário'}) já tem relatório finalizado "
                        f"por {quem}: {mesma_aula.nome_ficheiro_gerado or mesma_aula.conteudo_ministrado}. "
                        "Este rascunho é uma duplicata: exclua-o ou edite o relatório que já existe."
                    ),
                )
            # 2) Outro horário da mesma disciplina no dia (geminada): o sufixo P1/P2/P3 é
            #    colocado sozinho pela ordem dos horários, sem travar a finalização.
            if not verificar_sufixo_geminada(report.conteudo_ministrado):
                sufixo = _sufixo_geminada(report, aulas_existentes)
                novo = f"{(report.conteudo_ministrado or '').strip()} {sufixo}".strip()
                if len(novo) > LIMITE_CONTEUDO_MINISTRADO:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Aula geminada: já existe outra aula desta disciplina para a turma neste dia. "
                            f"Encurte o conteúdo ministrado para caber o sufixo '{sufixo}' "
                            f"(máx. {LIMITE_CONTEUDO_MINISTRADO} caracteres)."
                        ),
                    )
                report.conteudo_ministrado = novo
                nome_gerado = gerar_nome_padronizado(
                    nomenclatura_turma=turma.nomenclatura_padrao or turma.nome,
                    disciplina=disciplina.nome if disciplina else "",
                    data_aula=report.data_aula,
                    conteudo=report.conteudo_ministrado,
                    modalidade=turma.modalidade,
                )
            report.conflito_geminada_resolvido = True

    # v4 (restaurado de 19/08), depois do sufixo P1/P2 da geminada: mesmo arquivo na mesma data e slot repetido entre
    # relatórios finalizados. Outros rascunhos no slot não bloqueiam.
    _validar_ficheiro_duplicado(db, report.data_aula, nome_gerado, exclude_report_id=report.id)
    _validar_slot_unico(
        db, report.turma_id, report.data_aula, report.horario_aula, report.disciplina_id,
        exclude_report_id=report.id, only_finalizados=True, tipo_aula=report.tipo_aula,
    )

    # Validar slot da grade oficial (Apenas na finalização) — Pula para tipos especiais
    # (BUGFIX: antes só pulava "Gravação estúdio", deixando "Gravação externa" e
    # "Manutenção de estúdio" caírem na validação de grade regular por engano)
    if report.tipo_aula not in TIPOS_ESPECIAIS:
        _validar_slot_grade(
            db,
            report.turma_id,
            report.data_aula,
            report.disciplina_id,
            report.horario_aula,
            report.regular,
            start_time=report.start_time,
        )

    # Verificar choque de horário antes de finalizar — Pula para tipos especiais
    # (BUGFIX: mesma correção acima, aplicada ao choque de horário)
    # Se start_time ou end_time forem None (horário não mapeado),
    # ignorar silenciosamente e prosseguir com a finalização normalmente
    if report.start_time and report.end_time and report.tipo_aula not in TIPOS_ESPECIAIS:
        _verificar_choque_horario(
            db,
            report.data_aula,
            report.estudio,
            report.start_time,
            report.end_time,
            exclude_id=report.id,
            canal_utilizado=report.canal_utilizado,
            # v4: antes comparava com "Gravação", valor que não existe no enum;
            # os tipos de gravação já pulam este bloco (TIPOS_ESPECIAIS).
            is_gravacao=False,
            turma_id=report.turma_id,
            tipo_aula=report.tipo_aula,
        )


    # Data da gravação × data da aula na grade (reposição / antecipada) e o indicativo
    ajustar_datas_gravacao(report)
    _professor_da_exibicao(report)
    _aplicar_link_da_agenda(db, report)

    # Demanda 1.1 e 138: Trava de consistência de faturamento com relatório do Diretor de Imagem
    idr_correspondente = buscar_image_director_por_class_report(db, report)
    validar_consistencia_faturamento(report, idr_correspondente)

    # Só então finaliza — v3.1: vai para AGUARDANDO_VALIDACAO (fila da Coordenação),
    # não mais direto para FINALIZADO. Se o relatório vinha de uma correção,
    # limpa a flag e a observação da coordenação.
    report.nome_ficheiro_gerado = nome_gerado
    report.nome_normalizado = normalizar_para_match(nome_gerado)
    report.status = novo_status
    report.precisa_correcao = False
    report.observacao_coordenacao = None

    vincular_image_director_ao_class_report(db, report)
    registrar_versao(db, TIPO_AULA, report, "FINALIZADO", current_user, status_anterior=status_anterior)
    db.commit()
    db.refresh(report)

    # TASK 06: Broadcast WebSocket
    _broadcast_report_update("FINALIZED", str(report.id), current_user.full_name)

    # Agenda a verificação de compliance com ATRASO INICIAL (§6): finaliza →
    # Pendente → aguarda ~2,5h (o arquivo só chega ao Drive depois) → verifica.
    try:
        from app.services.tarefas import agendar_verificacao
        agendar_verificacao(report.id, nome_gerado)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"Não foi possível disparar verificação de compliance: {e}"
        )

    return report


@router.get("/{report_id}/conferencia-par")
def conferencia_do_par(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """O que não bate entre este relatório e o do diretor de imagem da mesma aula (aviso antes de validar)."""
    report = db.query(ClassReport).filter(
        ClassReport.id == report_id,
        ClassReport.is_deleted == False,  # noqa: E712
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")
    idr = buscar_image_director_por_class_report(db, report)
    return {
        "tem_par": bool(idr),
        "par_id": str(idr.id) if idr else None,
        "divergencias": divergencias_do_par(report, idr) if idr else [],
    }


@router.patch("/{report_id}/validar", response_model=ClassReportResponse, dependencies=_WRITE_DEPS)
def validar_relatorio(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_COORDENACAO)),
):
    """
    v3.1 — Validação da Coordenação: a coordenadora confere professor, conteúdo
    ministrado, PDF, vídeo bruto e o preenchimento do formulário, e marca o
    relatório como VALIDADO.
    """
    report = db.query(ClassReport).filter(
        ClassReport.id == report_id,
        ClassReport.is_deleted == False,  # noqa: E712
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")

    status_anterior = report.status
    novo_status = estados.destino("validar", report.status)
    # Reunião (out/2026): a coordenação só valida com os dois links (vídeo e PDF) coletados
    from app.services.busca_links import links_coletados
    if not links_coletados(report):
        faltam = [n for n, v in (("vídeo", report.video_link), ("PDF", report.slide_link)) if not (v or "").strip()]
        raise HTTPException(
            status_code=400,
            detail=f"Ainda falta coletar o link do {' e do '.join(faltam)} no Drive. A validação libera quando os dois links forem coletados.",
        )

    report.status = novo_status
    report.precisa_correcao = False
    report.observacao_coordenacao = None
    report.validado_por = current_user.id
    report.validado_em = datetime.now(timezone.utc)
    registrar_versao(db, TIPO_AULA, report, "VALIDADO", current_user, status_anterior=status_anterior)

    log = AuditLog(
        actor_id=current_user.id,
        action="VALIDATE_REPORT",
        details=f"{current_user.full_name} validou o relatório {report.id}",
    )
    db.add(log)
    db.commit()
    db.refresh(report)

    _broadcast_report_update("VALIDATED", str(report.id), current_user.full_name)

    return report


@router.patch("/{report_id}/solicitar-correcao", response_model=ClassReportResponse, dependencies=_WRITE_DEPS)
def solicitar_correcao_relatorio(
    report_id: UUID,
    payload: ClassReportSolicitarCorrecao,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_COORDENACAO)),
):
    """
    v3.1 — Devolve o relatório para o Assistente corrigir: volta para RASCUNHO
    com precisa_correcao=True e a observação da Coordenação anexada.
    """
    report = db.query(ClassReport).filter(
        ClassReport.id == report_id,
        ClassReport.is_deleted == False,  # noqa: E712
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")

    status_anterior = report.status
    report.status = estados.destino("devolver", report.status)
    report.precisa_correcao = True
    report.observacao_coordenacao = payload.observacao_coordenacao
    report.validado_por = None
    report.validado_em = None
    registrar_versao(
        db, TIPO_AULA, report, "DEVOLVIDO", current_user,
        status_anterior=status_anterior, motivo=payload.observacao_coordenacao,
    )

    log = AuditLog(
        actor_id=current_user.id,
        action="REQUEST_REPORT_CORRECTION",
        details=(
            f"{current_user.full_name} solicitou correção do relatório {report.id}: "
            f"{payload.observacao_coordenacao}"
        ),
    )
    db.add(log)
    db.commit()
    db.refresh(report)

    _broadcast_report_update("CORRECTION_REQUESTED", str(report.id), current_user.full_name)

    # TODO (opcional): disparar e-mail para report.creator.email avisando da correção,
    # reaproveitando o serviço de SMTP já configurado no .env.

    return report


# ─── CQRS: Endpoint de Estatísticas (TASK 05) ────────────────────────


@router.get("/stats")
def dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    CQRS Query: Retorna contagens agregadas direto do banco para o Dashboard.
    Evita carregar 200+ itens em memória para contar no frontend.
    """
    today = date.today()
    total_today = db.query(func.count(ClassReport.id)).filter(
        ClassReport.data_aula == today,
        ClassReport.is_deleted == False,  # noqa: E712
    ).scalar() or 0

    # v3.1: granular por etapa do fluxo de validação
    aguardando_validacao = db.query(func.count(ClassReport.id)).filter(
        ClassReport.status == "AGUARDANDO_VALIDACAO",
        ClassReport.is_deleted == False,  # noqa: E712
    ).scalar() or 0

    validados = db.query(func.count(ClassReport.id)).filter(
        ClassReport.status == "VALIDADO",
        ClassReport.is_deleted == False,  # noqa: E712
    ).scalar() or 0

    # Mantido por compatibilidade: soma tudo que não é rascunho/cancelado
    # (cobre também registros antigos com status FINALIZADO).
    finalized = db.query(func.count(ClassReport.id)).filter(
        ClassReport.status.in_(STATUS_FINALIZADOS),
        ClassReport.is_deleted == False,  # noqa: E712
    ).scalar() or 0

    drafts = db.query(func.count(ClassReport.id)).filter(
        ClassReport.status == "RASCUNHO",
        ClassReport.is_deleted == False,  # noqa: E712
    ).scalar() or 0

    precisa_correcao = db.query(func.count(ClassReport.id)).filter(
        ClassReport.precisa_correcao == True,  # noqa: E712
        ClassReport.is_deleted == False,  # noqa: E712
    ).scalar() or 0

    cancelled = db.query(func.count(ClassReport.id)).filter(
        ClassReport.status == "CANCELADO",
        ClassReport.is_deleted == False,  # noqa: E712
    ).scalar() or 0

    total = db.query(func.count(ClassReport.id)).filter(
        ClassReport.is_deleted == False,  # noqa: E712
    ).scalar() or 0

    return {
        "total_today": total_today,
        "finalized": finalized,
        "aguardando_validacao": aguardando_validacao,
        "validados": validados,
        "precisa_correcao": precisa_correcao,
        "drafts": drafts,
        "cancelled": cancelled,
        "total": total,
    }


@router.get("/status-resumo")
def resumo_por_status(
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    turma_id: Optional[UUID] = Query(None),
    professor_id: Optional[UUID] = Query(None),
    disciplina_id: Optional[UUID] = Query(None),
    estudio: Optional[str] = Query(None),
    tipo_aula: Optional[str] = Query(None),
    com_atraso: Optional[bool] = Query(None),
    com_substituicao: Optional[bool] = Query(None),
    com_problema: Optional[bool] = Query(None),
    precisa_correcao: Optional[bool] = Query(None),
    created_by: Optional[UUID] = Query(None),
    modalidade_aula: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Quantidade de relatórios de aula por status (Rascunho, Aguardando Validação,
    Validado, Cancelado...) com os MESMOS filtros da lista, exceto o próprio status —
    para a Auditoria mostrar quanto falta em cada etapa.
    """
    q = _apply_report_filters(
        db.query(ClassReport.status, func.count(ClassReport.id)),
        db=db,
        data_inicio=data_inicio,
        data_fim=data_fim,
        turma_id=turma_id,
        professor_id=professor_id,
        disciplina_id=disciplina_id,
        estudio=estudio,
        tipo_aula=tipo_aula,
        com_atraso=com_atraso,
        com_substituicao=com_substituicao,
        com_problema=com_problema,
        created_by=created_by,
        precisa_correcao=precisa_correcao,
        modalidade_aula=modalidade_aula,
    )
    contagem = {st or "": n for st, n in q.group_by(ClassReport.status).all()}

    correcao_q = _apply_report_filters(
        db.query(func.count(ClassReport.id)),
        db=db,
        data_inicio=data_inicio,
        data_fim=data_fim,
        turma_id=turma_id,
        professor_id=professor_id,
        disciplina_id=disciplina_id,
        estudio=estudio,
        tipo_aula=tipo_aula,
        com_atraso=com_atraso,
        com_substituicao=com_substituicao,
        com_problema=com_problema,
        created_by=created_by,
        modalidade_aula=modalidade_aula,
    ).filter(ClassReport.precisa_correcao == True)  # noqa: E712

    rascunho = contagem.get("RASCUNHO", 0)
    aguardando = contagem.get("AGUARDANDO_VALIDACAO", 0)
    validado = contagem.get("VALIDADO", 0)
    cancelado = contagem.get("CANCELADO", 0)
    finalizado_legado = contagem.get("FINALIZADO", 0)
    filtros_fila = dict(
        db=db, data_inicio=data_inicio, data_fim=data_fim, turma_id=turma_id, professor_id=professor_id,
        disciplina_id=disciplina_id, estudio=estudio, tipo_aula=tipo_aula, com_atraso=com_atraso,
        com_substituicao=com_substituicao, com_problema=com_problema, created_by=created_by,
        precisa_correcao=precisa_correcao, modalidade_aula=modalidade_aula,
    )
    prontos = _apply_report_filters(
        db.query(func.count(ClassReport.id)), fila_validacao="prontos", **filtros_fila
    ).scalar() or 0
    return {
        # Fila da coordenação: prontos (vídeo e PDF coletados) × ainda esperando os links
        "prontos_para_validar": prontos,
        "aguardando_links": max(aguardando - prontos, 0),
        "rascunho": rascunho,
        "aguardando_validacao": aguardando,
        "validado": validado,
        "cancelado": cancelado,
        "finalizado_legado": finalizado_legado,
        "precisa_correcao": correcao_q.scalar() or 0,
        # Ainda não validados: em rascunho (inclui devolvidos) + na fila de validação
        "faltam_validar": rascunho + aguardando,
        "total": sum(contagem.values()),
    }


@router.get("/professor-resumo")
def resumo_do_professor(
    professor_id: UUID = Query(...),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    turma_id: Optional[UUID] = Query(None),
    disciplina_id: Optional[UUID] = Query(None),
    estudio: Optional[str] = Query(None),
    tipo_aula: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    modalidade_aula: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Reunião 26/10/2026 — painel por professor (só visualização):
    - total de aulas: 1 por slot (relatório), qualquer que seja a duração;
    - total de horas: soma do tempo real de cada aula (aula da noite de 45 min conta 45).
    A interpretação do pagamento (hora-aula) é de quem paga. Cancelados não contam;
    a exibição de aula gravada antes não tem professor, então não conta duas vezes.
    """
    from app.services.audit_export import _class_horario_str
    from app.services.uso_estudio import _horas_do_texto, _minutos, fmt_minutos

    q = _apply_report_filters(
        db.query(ClassReport),
        db=db,
        data_inicio=data_inicio,
        data_fim=data_fim,
        turma_id=turma_id,
        professor_id=professor_id,
        disciplina_id=disciplina_id,
        estudio=estudio,
        tipo_aula=tipo_aula,
        status_filter=status_filter,
        modalidade_aula=modalidade_aula,
    ).filter(ClassReport.status != "CANCELADO")
    reports = q.all()
    turmas = {t.id: t for t in db.query(Turma).filter(Turma.id.in_({r.turma_id for r in reports if r.turma_id})).all()} if reports else {}
    total_min = 0
    sem_horario = 0
    for r in reports:
        ini, fim = _horas_do_texto(_class_horario_str(r, turmas.get(r.turma_id)))
        m = _minutos(ini, fim)
        if m is None:
            sem_horario += 1
            continue
        total_min += m
    return {
        "professor_id": str(professor_id),
        "total_aulas": len(reports),
        "total_minutos": total_min,
        "total_horas": fmt_minutos(total_min),
        "aulas_sem_horario": sem_horario,
    }


@router.get("/status-semana")
def get_status_semana(
    turma_id: UUID,
    data_inicio: date,
    data_fim: date,
    db: Session = Depends(get_db)
):
    if data_inicio > data_fim:
        raise HTTPException(
            status_code=422,
            detail="data_inicio não pode ser maior que data_fim"
        )

    registros = db.query(ClassReport).filter(
        ClassReport.turma_id == turma_id,
        ClassReport.data_aula >= data_inicio,
        ClassReport.data_aula <= data_fim,
        ClassReport.horario_aula.isnot(None),
        ClassReport.is_deleted == False
    ).all()

    return {
        f"{r.data_aula.isoformat()}:{r.horario_aula}": {
            "id": r.id,
            "status": r.status
        } for r in registros
    }


@router.post("/force-sync-drive", status_code=status.HTTP_202_ACCEPTED, dependencies=_WRITE_DEPS)
def forcar_sincronizacao_drive(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Dispara varredura geral para forçar a sincronização de relatórios Pendentes.
    """
    from app.services.tarefas import varrer

    try:
        r = varrer(db)
        corrigidos = r["corrigidos_verde"]
        if r["modo"] == "celery":
            msg = "Sincronização em massa enviada para a fila com sucesso."
        else:
            # v4.1 (sem worker): a busca rodou agora mesmo
            msg = (f"Busca no Drive feita em {r['verificados']} relatório(s): "
                   f"{r['verdes']} completo(s), {r['faltando']} ainda esperando arquivo"
                   + (f", {r['vermelhos']} passaram do prazo (Vermelho)" if r['vermelhos'] else "") + ".")
            if r["restantes"]:
                msg += f" Faltaram {r['restantes']}; clique de novo para continuar."
        if corrigidos:
            msg += f" {corrigidos} relatório(s) com vídeo e PDF já foram marcados como Verde."
        return {"message": msg, "corrigidos_verde": corrigidos, "detalhes": r}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Não foi possível agendar a verificação no Drive agora. Tente de novo em alguns minutos.")


@router.post("/{report_id}/sync-individual", status_code=status.HTTP_202_ACCEPTED, dependencies=_WRITE_DEPS)
def sync_individual(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Dispara sincronização manual pontual para um único relatório.
    """
    # ✅ Soft delete: ignora relatórios arquivados
    report = db.query(ClassReport).filter(
        ClassReport.id == report_id,
        ClassReport.is_deleted == False,  # noqa: E712
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")
    if not report.nome_ficheiro_gerado:
        raise HTTPException(
            status_code=400,
            detail="Relatório sem nome de arquivo gerado. Finalize o relatório antes de reverificar.",
        )

    report.status_compliance = "Pendente"
    db.commit()
    db.refresh(report)

    from app.services.busca_links import VIDEO_CORROMPIDO, bloqueio_busca_link
    motivo = bloqueio_busca_link(db, report, exigir_diretor=False)
    if motivo == VIDEO_CORROMPIDO:
        raise HTTPException(
            status_code=409,
            detail="O diretor de imagem marcou o vídeo como corrompido. Quando ele recuperar o vídeo, "
                   "desmarcar e salvar o relatório dele, a busca do link começa.",
        )
    from app.services.tarefas import verificar_agora
    try:
        r = verificar_agora(report.id, report.nome_ficheiro_gerado, exigir_diretor=False)
        if r["modo"] == "celery":
            return {"message": "Sincronização individual iniciada."}
        textos = {"verde": "Vídeo e PDF encontrados no Drive.",
                  "faltou": "Ainda falta arquivo no Drive; o relatório continua Pendente.",
                  "adiado": "A busca está esperando o relatório do diretor de imagem.",
                  "ignorado": "Este relatório não precisa de busca agora."}
        return {"message": textos.get(r["resultado"], "Verificação feita."), "resultado": r["resultado"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Não foi possível agendar a verificação no Drive agora. Tente de novo em alguns minutos.")


@router.patch("/{report_id}/cancelar", response_model=ClassReportResponse, dependencies=_WRITE_DEPS)
def cancelar_relatorio(
    report_id: UUID,
    cancel_data: ClassReportCancel,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Cancela um relatório com justificativa obrigatória."""
    # ✅ Soft delete: ignora relatórios arquivados
    report = db.query(ClassReport).filter(
        ClassReport.id == report_id,
        ClassReport.is_deleted == False,  # noqa: E712
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")

    politicas.exigir(current_user, "relatorio_aula.cancelar", autor_id=report.created_by)
    status_anterior = report.status
    novo_status = estados.destino("cancelar", report.status)
    # v4: relatório já validado (base da cobrança) só a coordenação cancela
    if status_anterior == estados.VALIDADO and not politicas.pode(current_user, "relatorio_aula.validar"):
        raise HTTPException(
            status_code=403,
            detail="Este relatório já foi validado. Só a coordenação pode cancelá-lo.",
        )

    # v4: a justificativa tem campo próprio; as observações do assistente ficam intactas
    report.status = novo_status
    report.justificativa_cancelamento = cancel_data.justificativa
    report.cancelado_por = current_user.id
    report.cancelado_em = datetime.now(timezone.utc)
    registrar_versao(
        db, TIPO_AULA, report, "CANCELADO", current_user,
        status_anterior=status_anterior, motivo=cancel_data.justificativa,
    )
    db.add(AuditLog(
        actor_id=current_user.id,
        action="REPORT_CANCELLED",
        details=f"{current_user.full_name} cancelou o relatório {report.id}: {cancel_data.justificativa}",
    ))

    db.commit()
    db.refresh(report)

    # TASK 06: Broadcast WebSocket
    _broadcast_report_update("CANCELLED", str(report.id), current_user.full_name)

    return report


@router.get("/", response_model=PaginatedReportsResponse)
def listar_relatorios(
    data_aula: Optional[date] = Query(None),
    data_inicio: Optional[date] = Query(None, description="Filtro período início"),
    data_fim: Optional[date] = Query(None, description="Filtro período fim"),
    turma_id: Optional[UUID] = Query(None),
    professor_id: Optional[UUID] = Query(None),
    disciplina_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    estudio: Optional[str] = Query(None),
    tipo_aula: Optional[str] = Query(None),
    com_atraso: Optional[bool] = Query(None, description="Filtrar com atraso"),
    com_substituicao: Optional[bool] = Query(None, description="Filtrar com substituição"),
    com_problema: Optional[bool] = Query(None, description="Filtrar com problema técnico"),
    precisa_correcao: Optional[bool] = Query(None, description="Filtrar relatórios devolvidos para correção"),
    created_by: Optional[UUID] = Query(None, description="Filtrar por usuário/assistente"),
    modalidade_aula: Optional[str] = Query(None, description="gravacao | transmissao"),
    status_idr: Optional[str] = Query(None, description="Status do relatório do Diretor de Imagem (ou SEM_RELATORIO)"),
    fila_validacao: Optional[str] = Query(None, description="prontos (links coletados) | aguardando"),
    sort_by: str = Query("data_aula", description="Campo de ordenação: data_aula ou created_at"),
    sort_order: str = Query("desc", description="Ordem: asc ou desc"),
    limit: int = Query(50, ge=1, le=200, description="Itens por página"),
    offset: int = Query(0, ge=0, description="Offset para paginação"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lista relatórios com paginação server-side (§5.3).
    Padrão: 50 por página, ordenação decrescente por data_aula.
    """
    query = db.query(ClassReport)

    # Aplicar filtros (já inclui is_deleted == False internamente)
    query = _apply_report_filters(
        query,
        db=db,
        data_aula=data_aula,
        data_inicio=data_inicio,
        data_fim=data_fim,
        turma_id=turma_id,
        professor_id=professor_id,
        disciplina_id=disciplina_id,
        status_filter=status_filter,
        estudio=estudio,
        tipo_aula=tipo_aula,
        com_atraso=com_atraso,
        com_substituicao=com_substituicao,
        com_problema=com_problema,
        created_by=created_by,
        precisa_correcao=precisa_correcao,
        modalidade_aula=modalidade_aula,
        status_idr=status_idr,
        fila_validacao=fila_validacao,
    )

    # Contagem total (antes da paginação)
    total = query.count()

    # Ordenação (desempate alinhado ao /image-director/ para mesclagem na auditoria)
    sort_column = ClassReport.created_at if sort_by == "created_at" else ClassReport.data_aula
    if sort_order == "asc":
        query = query.order_by(
            sort_column.asc(),
            ClassReport.turno.asc(),
            ClassReport.estudio.asc(),
            ClassReport.horario_aula.asc(),
            ClassReport.created_at.desc(),
        )
    else:
        query = query.order_by(
            sort_column.desc(),
            ClassReport.turno.asc(),
            ClassReport.estudio.asc(),
            ClassReport.horario_aula.asc(),
            ClassReport.created_at.desc(),
        )

    # Paginação (+ relações para serialização segura)
    items = (
        _report_list_query_options(query)
        .offset(offset)
        .limit(limit)
        .all()
    )

    return PaginatedReportsResponse(
        items=[
            serialize_class_report(r, buscar_image_director_por_class_report(db, r))
            for r in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


PAPEIS_AUDITORIA_DUAL = ("admin", "gestor", "diretor_chefe")
# Reunião 26/10/2026: exportação só para quem fecha a cobrança
PAPEIS_EXPORTACAO = ("admin", "gestor", "coordenador", "coordenadora", "diretor_chefe")


@router.get("/auditoria")
def listar_auditoria_unificada(
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    turma_id: Optional[UUID] = Query(None),
    professor_id: Optional[UUID] = Query(None),
    disciplina_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    estudio: Optional[str] = Query(None),
    tipo_aula: Optional[str] = Query(None),
    com_atraso: Optional[bool] = Query(None),
    com_substituicao: Optional[bool] = Query(None),
    com_problema: Optional[bool] = Query(None),
    precisa_correcao: Optional[bool] = Query(None),
    created_by: Optional[UUID] = Query(None),
    modalidade_aula: Optional[str] = Query(None, description="gravacao | transmissao"),
    status_idr: Optional[str] = Query(None, description="Status do relatório do Diretor de Imagem (ou SEM_RELATORIO)"),
    fila_validacao: Optional[str] = Query(None, description="prontos (links coletados) | aguardando"),
    sort_by: str = Query("data_aula"),
    sort_order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_AUDITORIA_DUAL)),
):
    """
    Lista da Auditoria (assistente + diretor de imagem) com filtros, total e
    paginação calculados no servidor. Relatórios do diretor SEM relatório de aula
    vinculado entram na mesma ordenação — antes eram mesclados na tela página a
    página, o que duplicava/escondia linhas e distorcia o total.
    """
    from app.api.rotas_diretor_imagem import (
        _filtrar_idr_disciplina,
        _filtrar_idr_professor,
        build_idr_list_items,
    )
    from app.models.image_director_report import ImageDirectorLesson, ImageDirectorReport
    from app.services.filtros import estudio_variantes

    class_q = _apply_report_filters(
        db.query(ClassReport),
        db=db,
        data_inicio=data_inicio,
        data_fim=data_fim,
        turma_id=turma_id,
        professor_id=professor_id,
        disciplina_id=disciplina_id,
        status_filter=status_filter,
        estudio=estudio,
        tipo_aula=tipo_aula,
        com_atraso=com_atraso,
        com_substituicao=com_substituicao,
        com_problema=com_problema,
        created_by=created_by,
        precisa_correcao=precisa_correcao,
        modalidade_aula=modalidade_aula,
        status_idr=status_idr,
        fila_validacao=fila_validacao,
    )
    usar_created = sort_by == "created_at"
    class_keys = [
        ("c", rid, (dt_created if usar_created else dt_aula), dt_created)
        for rid, dt_aula, dt_created in class_q.with_entities(
            ClassReport.id, ClassReport.data_aula, ClassReport.created_at
        ).all()
    ]

    # Filtros que só existem no relatório do assistente excluem as linhas "só diretor".
    filtros_so_assistente = any([
        status_filter, tipo_aula, com_atraso, com_substituicao, com_problema, created_by, fila_validacao,
    ])
    idr_keys = []
    # Aulas sem relatório do diretor não têm linha "só diretor"
    if (status_idr or "").strip().upper() == "SEM_RELATORIO":
        filtros_so_assistente = True
    if not filtros_so_assistente:
        idr_q = db.query(ImageDirectorReport).filter(ImageDirectorReport.is_deleted == False)  # noqa: E712
        if data_inicio:
            idr_q = idr_q.filter(ImageDirectorReport.data_relatorio >= data_inicio)
        if data_fim:
            idr_q = idr_q.filter(ImageDirectorReport.data_relatorio <= data_fim)
        if turma_id:
            idr_q = idr_q.filter(ImageDirectorReport.turma_id == turma_id)
        if estudio:
            idr_q = idr_q.filter(
                ImageDirectorReport.estudio.in_(estudio_variantes(db, ImageDirectorReport.estudio, estudio))
            )
        if professor_id:
            idr_q = _filtrar_idr_professor(db, idr_q, professor_id)
        if disciplina_id:
            idr_q = _filtrar_idr_disciplina(db, idr_q, disciplina_id)
        if precisa_correcao is not None:
            idr_q = idr_q.filter(ImageDirectorReport.precisa_correcao == precisa_correcao)
        if status_idr:
            idr_q = idr_q.filter(ImageDirectorReport.status == status_idr.strip().upper())
        if modalidade_aula:
            tipo_lesson = "Aula gravada" if _validar_modalidade(modalidade_aula) == "gravacao" else "Transmissão"
            com_tipo = db.query(ImageDirectorLesson.report_id).filter(
                ImageDirectorLesson.transmissao_ou_gravada == tipo_lesson
            )
            idr_q = idr_q.filter(ImageDirectorReport.id.in_(com_tipo))
        vinculados = db.query(ImageDirectorLesson.report_id).filter(ImageDirectorLesson.class_report_id.isnot(None))
        idr_q = idr_q.filter(
            ImageDirectorReport.class_report_id.is_(None),
            ~ImageDirectorReport.id.in_(vinculados),
        )
        idr_keys = [
            ("i", rid, (dt_created if usar_created else dt_rel), dt_created)
            for rid, dt_rel, dt_created in idr_q.with_entities(
                ImageDirectorReport.id, ImageDirectorReport.data_relatorio, ImageDirectorReport.created_at
            ).all()
        ]

    def _k(item):
        _, rid, principal, criado = item
        p = principal.isoformat() if principal else ""
        c = criado.isoformat() if criado else ""
        return (p, c, str(rid))

    todos = sorted(class_keys + idr_keys, key=_k, reverse=(sort_order != "asc"))
    total = len(todos)
    pagina = todos[offset: offset + limit]

    class_ids = [rid for t, rid, *_ in pagina if t == "c"]
    idr_ids = [rid for t, rid, *_ in pagina if t == "i"]
    class_map = {}
    if class_ids:
        class_map = {
            r.id: r
            for r in _report_list_query_options(db.query(ClassReport)).filter(ClassReport.id.in_(class_ids)).all()
        }
    idr_map = {}
    if idr_ids:
        idr_objs = db.query(ImageDirectorReport).filter(ImageDirectorReport.id.in_(idr_ids)).all()
        idr_map = {item.id: item for item in build_idr_list_items(db, idr_objs)}

    items = []
    for t, rid, *_ in pagina:
        if t == "c" and rid in class_map:
            r = class_map[rid]
            items.append({
                "tipo": "class",
                "data": serialize_class_report(r, buscar_image_director_por_class_report(db, r)),
            })
        elif t == "i" and rid in idr_map:
            items.append({"tipo": "idr", "data": idr_map[rid]})
    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ─── Manutenção: relatórios legados "FINALIZADO" ─────────────────────
# O fluxo de validação (AGUARDANDO_VALIDACAO → VALIDADO) entrou em produção em
# 01/09/2026. Relatórios finalizados ANTES disso ficaram com o status legado
# FINALIZADO. Os de aulas até 31/08 continuam como legado; os de aulas a partir
# de 01/09 (gravadas antecipadamente) precisam passar pela validação.
DATA_INICIO_FLUXO_VALIDACAO = date(2026, 9, 1)


@router.post("/admin/finalizados-para-validacao")
def migrar_finalizados_para_validacao(
    aplicar: bool = Query(False, description="false = só lista (simulação); true = aplica a mudança"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """
    Envia para 'Aguardando Validação' os relatórios com status legado FINALIZADO
    cuja data da aula é a partir de 01/09/2026. Idempotente.
    """
    alvos = (
        _report_list_query_options(db.query(ClassReport))
        .filter(
            ClassReport.status == "FINALIZADO",
            ClassReport.is_deleted == False,  # noqa: E712
            ClassReport.data_aula >= DATA_INICIO_FLUXO_VALIDACAO,
        )
        .order_by(ClassReport.data_aula, ClassReport.turma_id)
        .all()
    )
    lista = [
        {
            "id": str(r.id),
            "data_aula": r.data_aula.isoformat(),
            "turma": r.turma_nome,
            "disciplina": r.disciplina_nome,
            "horario": r.horario_aula,
            "criado_por": r.creator_name,
        }
        for r in alvos
    ]
    if aplicar and alvos:
        for r in alvos:
            r.status = "AGUARDANDO_VALIDACAO"
            r.precisa_correcao = False
        db.add(AuditLog(
            actor_id=current_user.id,
            action="MIGRATE_FINALIZADO_TO_VALIDATION",
            details=(
                f"{current_user.full_name} enviou {len(alvos)} relatório(s) FINALIZADO "
                f"(aulas a partir de {DATA_INICIO_FLUXO_VALIDACAO.strftime('%d/%m/%Y')}) para validação."
            ),
        ))
        db.commit()
    return {
        "aplicado": bool(aplicar and alvos),
        "total": len(lista),
        "relatorios": lista,
    }


@router.get("/export")
@router.get("/export/xlsm")
@router.get("/export.xlsm")
def exportar_relatorios(
    request: Request,
    data_aula: Optional[date] = Query(None),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    turma_id: Optional[UUID] = Query(None),
    professor_id: Optional[UUID] = Query(None),
    disciplina_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    estudio: Optional[str] = Query(None),
    tipo_aula: Optional[str] = Query(None),
    com_atraso: Optional[bool] = Query(None),
    com_substituicao: Optional[bool] = Query(None),
    com_problema: Optional[bool] = Query(None),
    precisa_correcao: Optional[bool] = Query(None),
    created_by: Optional[UUID] = Query(None),
    modalidade_aula: Optional[str] = Query(None, description="gravacao | transmissao"),
    status_idr: Optional[str] = Query(None, description="Status do relatório do Diretor de Imagem (ou SEM_RELATORIO)"),
    formato: str = Query("xlsx", regex="^(xlsx|xlsm)$", description="xlsx ou xlsm (macro-enabled)"),
    include_faturamento: bool = Query(False, description="Incluir aba Faturamento SEDUC"),
    modelo: Optional[str] = Query(
        None, regex="^(uso_estudio|detalhado)$",
        description="uso_estudio (planilha única, uma linha por hora — padrão do .xlsx) ou detalhado (abas antigas)",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*PAPEIS_EXPORTACAO)),
):
    """
    Exporta workbook Excel (3 ou 4 abas: Faturamento SEDUC, Consolidado, Assistente, Diretor Imagem)
    respeitando filtros ativos do painel de auditoria e permissões do usuário (coordenador não vê Diretor de Imagem).
    """
    import logging

    from app.services.audit_export import AuditExportFilters, build_audit_workbook

    logger = logging.getLogger(__name__)

    # Se a rota acessada for explicitamente /export/xlsm ou /export.xlsm, forçar formato xlsm
    path = request.url.path if request else ""
    if "xlsm" in path:
        formato = "xlsm"

    is_xlsm = (formato == "xlsm")
    include_fat = True if is_xlsm else include_faturamento

    filters = AuditExportFilters(
        data_aula=data_aula,
        data_inicio=data_inicio,
        data_fim=data_fim,
        turma_id=turma_id,
        professor_id=professor_id,
        disciplina_id=disciplina_id,
        status_filter=status_filter,
        estudio=estudio,
        tipo_aula=tipo_aula,
        com_atraso=com_atraso,
        com_substituicao=com_substituicao,
        com_problema=com_problema,
        precisa_correcao=precisa_correcao,
        created_by=created_by,
        modalidade_aula=modalidade_aula,
        status_idr=status_idr,
    )
    # Reunião 26/10/2026: o .xlsx padrão é a planilha única "Uso de Estúdio"
    modelo_final = modelo or ("detalhado" if is_xlsm else "uso_estudio")
    try:
        if modelo_final == "uso_estudio" and not is_xlsm:
            from app.services.uso_estudio import build_uso_estudio_workbook

            file_bytes = build_uso_estudio_workbook(db, filters, user_role=current_user.role)
        else:
            file_bytes = build_audit_workbook(
                db,
                filters,
                user_role=current_user.role,
                is_xlsm=is_xlsm,
                include_faturamento=include_fat,
            )
    except Exception:
        logger.exception("Falha ao gerar exportação combinada de auditoria")
        raise HTTPException(status_code=500, detail="Erro ao gerar exportação Excel.")

    if is_xlsm:
        media_type = "application/vnd.ms-excel.sheet.macroEnabled.12"
        filename = f"relatorios_faturamento_seduc_{date.today().strftime('%Y-%m-%d')}.xlsm"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = (
            f"uso_de_estudio_{date.today().strftime('%Y-%m-%d')}.xlsx"
            if modelo_final == "uso_estudio"
            else f"relatorios_audit_{date.today().strftime('%Y-%m-%d')}.xlsx"
        )

    return StreamingResponse(
        iter([file_bytes]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _carregar_professores_vinculados_por_disciplina(db: Session):
    """
    v4 (restaurado de 21/08): disciplinas com pelo menos um professor ATIVO e o
    mapa disciplina_id -> [nomes]. Separa, na auditoria, aula pendente "com
    professor" (falta relatório) de "sem professor vinculado" (falta cadastro).
    """
    rows = (
        db.query(ProfessorDisciplina.disciplina_id, Professor.nome)
        .join(Professor, ProfessorDisciplina.professor_id == Professor.id)
        .filter(Professor.is_active == True)  # noqa: E712
        .all()
    )
    disciplinas_com_professor = set()
    professores_por_disciplina: dict = {}
    for disc_id, prof_nome in rows:
        disciplinas_com_professor.add(disc_id)
        professores_por_disciplina.setdefault(disc_id, [])
        if prof_nome not in professores_por_disciplina[disc_id]:
            professores_por_disciplina[disc_id].append(prof_nome)
    for disc_id in professores_por_disciplina:
        professores_por_disciplina[disc_id].sort()
    return disciplinas_com_professor, professores_por_disciplina


@router.get("/audit-stats")
def audit_stats(
    data_inicio: date,
    data_fim: date,
    turma_id: Optional[UUID] = Query(None),
    professor_id: Optional[UUID] = Query(None),
    disciplina_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    estudio: Optional[str] = Query(None),
    tipo_aula: Optional[str] = Query(None),
    com_atraso: Optional[bool] = Query(None),
    com_substituicao: Optional[bool] = Query(None),
    com_problema: Optional[bool] = Query(None),
    precisa_correcao: Optional[bool] = Query(None),
    created_by: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Retorna as estatísticas de auditoria (Previstos vs Encontrados) e lista as pendências.
    """
    # 1. Base Query para Reports
    reports_query = db.query(ClassReport)
    reports_query = _apply_report_filters(
        reports_query,
        db=db,
        data_aula=None,
        data_inicio=data_inicio,
        data_fim=data_fim,
        turma_id=turma_id,
        professor_id=professor_id,
        disciplina_id=disciplina_id,
        status_filter=status_filter,
        estudio=estudio,
        tipo_aula=tipo_aula,
        com_atraso=com_atraso,
        com_substituicao=com_substituicao,
        com_problema=com_problema,
        precisa_correcao=precisa_correcao,
        created_by=created_by,
    )

    reports_in_period = reports_query.filter(ClassReport.status.in_(STATUS_FINALIZADOS)).all()
    total_relatorios = reports_query.count()

    # 2. Base Query para Grades (suporta slots legados sem versão e slots de versão ativa)
    from app.models.infraestrutura import GradeVersao, Estudio
    from datetime import timedelta, datetime
    from sqlalchemy import or_
    import re

    grade_query = db.query(Grade).join(Turma).filter(
        Turma.is_active == True
    )
    grade_query = grade_query.outerjoin(GradeVersao).filter(
        or_(
            Grade.grade_versao_id.is_(None),
            GradeVersao.is_active == True
        )
    )
    from app.services.filtros import (
        disciplina_equivalentes,
        estudio_variantes,
        professor_equivalentes,
    )

    if (data_fim - data_inicio).days > 366:
        raise HTTPException(status_code=422, detail="Período máximo da auditoria: 1 ano.")
    if turma_id:
        grade_query = grade_query.filter(Grade.turma_id == turma_id)
    if professor_id:
        prof_ids, _ = professor_equivalentes(db, professor_id)
        grade_query = grade_query.filter(Grade.professor_id.in_(prof_ids))
    if disciplina_id:
        disc_ids, _ = disciplina_equivalentes(db, disciplina_id)
        grade_query = grade_query.filter(Grade.disciplina_id.in_(disc_ids))
    if estudio:
        grade_query = grade_query.join(Estudio, Grade.estudio_id == Estudio.id).filter(
            Estudio.nome.in_(estudio_variantes(db, Estudio.nome, estudio))
        )

    slots_ativos = grade_query.all()
    # Turma com versão ativa da Grade v2: ignora slots legados (sem versão) para não contar em dobro
    turmas_com_versao = {s.turma_id for s in slots_ativos if s.grade_versao_id is not None}
    slots_ativos = [
        s for s in slots_ativos
        if s.grade_versao_id is not None or s.turma_id not in turmas_com_versao
    ]

    def normalize_to_digits(s: str) -> str:
        if not s:
            return ""
        digits = re.sub(r"\D", "", s)
        if digits:
            return digits
        return s.strip().upper()

    dias_pt = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    delta = data_fim - data_inicio
    
    total_grades = 0
    encontrados_ok = 0
    pendentes_detalhes = []
    sem_professor_detalhes = []
    disciplinas_com_professor, professores_por_disciplina = _carregar_professores_vinculados_por_disciplina(db)
    reports_matched = set()

    for i in range(delta.days + 1):
        dia_atual = data_inicio + timedelta(days=i)
        w_day = dia_atual.weekday()
        dia_str = dia_atual.strftime("%Y-%m-%d")

        slots_do_dia = []
        for s in slots_ativos:
            if s.dia_semana != w_day:
                continue
            if s.grade_versao_id is None:
                if s.vigencia_inicio and s.vigencia_inicio > dia_atual:
                    continue
                if s.vigencia_fim and s.vigencia_fim < dia_atual:
                    continue
            slots_do_dia.append(s)

        reports_do_dia = [r for r in reports_in_period if r.data_aula == dia_atual]

        for slot in slots_do_dia:
            total_grades += 1

            is_gravacao = (slot.horario_inicio.strftime("%H:%M") == "00:00") if slot.horario_inicio else False
            if is_gravacao:
                horario_label = "GRAVAÇÃO"
            else:
                h_ini = slot.horario_inicio.strftime("%H:%M") if slot.horario_inicio else ""
                h_fim = slot.horario_fim.strftime("%H:%M") if slot.horario_fim else ""
                horario_label = f"{h_ini} às {h_fim}"

            norm_grade_h = normalize_to_digits(horario_label)
            slot_disc_id_str = str(slot.disciplina_id) if slot.disciplina_id else "None"

            match_found = None

            # Passo 1: Match estrito por disciplina_id e horário
            for r in reports_do_dia:
                if r.id in reports_matched:
                    continue
                norm_report_h = normalize_to_digits(r.horario_aula)
                r_disc_id_str = str(r.disciplina_id) if r.disciplina_id else "None"

                if slot_disc_id_str == r_disc_id_str and norm_grade_h == norm_report_h:
                    match_found = r
                    break

            # Passo 2: Fallback por disciplina_id no mesmo dia
            if not match_found:
                for r in reports_do_dia:
                    if r.id in reports_matched:
                        continue
                    r_disc_id_str = str(r.disciplina_id) if r.disciplina_id else "None"
                    if slot_disc_id_str == r_disc_id_str:
                        match_found = r
                        break

            if match_found:
                encontrados_ok += 1
                reports_matched.add(match_found.id)
            else:
                h_ini = slot.horario_inicio.strftime("%H:%M") if slot.horario_inicio else "00:00"
                h_fim = slot.horario_fim.strftime("%H:%M") if slot.horario_fim else "00:00"
                horario_str = "GRAVAÇÃO" if h_ini == "00:00" else f"{h_ini} às {h_fim}"

                # Cálculo do padrão de semana ISO 8601
                iso_yr, iso_wk, _ = dia_atual.isocalendar()
                week_str = f"{iso_yr}-W{iso_wk:02d}"

                disc_id = slot.disciplina_id
                tem_professor = disc_id is not None and disc_id in disciplinas_com_professor
                profs_vinculados = professores_por_disciplina.get(disc_id, []) if disc_id else []
                if slot.professor and slot.professor.nome and slot.professor.nome not in profs_vinculados:
                    profs_vinculados = [slot.professor.nome] + profs_vinculados
                    tem_professor = True
                item = {
                    "data": dia_str,
                    "dia_semana": dias_pt[w_day],
                    "turma_id": str(slot.turma_id) if slot.turma_id else "",
                    "turma_nome": slot.turma.nomenclatura_padrao or slot.turma.nome if slot.turma else "N/A",
                    "disciplina_id": str(slot.disciplina_id) if slot.disciplina_id else "",
                    "disciplina_nome": slot.disciplina.nome if slot.disciplina else "N/A",
                    "professor_nome": ", ".join(profs_vinculados) if profs_vinculados else "Sem professor vinculado",
                    "professores_vinculados": profs_vinculados,
                    "tem_professor_associado": tem_professor,
                    "horario": horario_str,
                    "week": week_str,
                }
                if tem_professor:
                    pendentes_detalhes.append(item)
                else:
                    sem_professor_detalhes.append(item)

    extras = sum(1 for r in reports_in_period if r.id not in reports_matched)
    previstos_pendentes = len(pendentes_detalhes)

    return {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "previstos_pendentes": previstos_pendentes,
        "pendentes_operacionais": previstos_pendentes,
        "pendentes_sem_professor": len(sem_professor_detalhes),
        "sem_professor_detalhes": sem_professor_detalhes,
        "encontrados_ok": encontrados_ok,
        "extras": extras,
        "total_grades": total_grades,
        "total_relatorios": total_relatorios,
        "pendentes_detalhes": pendentes_detalhes,
    }


@router.get("/lookup/professores-por-disciplina/{disciplina_id}")
def listar_professores_por_disciplina(
    disciplina_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Retorna apenas os professores ATIVOS vinculados a uma disciplina específica.
    Usado pelo frontend para preencher o dropdown de professores.
    """
    professores = (
        db.query(Professor)
        .join(ProfessorDisciplina)
        .filter(ProfessorDisciplina.disciplina_id == disciplina_id)
        .filter(Professor.is_active == True)
        .all()
    )
    # Remove duplicates
    unique_professors = {p.id: p for p in professores}.values()
    return [{"id": str(p.id), "nome": p.nome} for p in sorted(unique_professors, key=lambda x: x.nome)]


@router.get("/{report_id}", response_model=ClassReportResponse)
def obter_relatorio(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Obtém detalhes de um relatório específico."""
    report = (
        _report_list_query_options(db.query(ClassReport))
        .filter(
            ClassReport.id == report_id,
            ClassReport.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")
    idr = buscar_image_director_por_class_report(db, report)
    return serialize_class_report(report, idr)


@router.put("/{report_id}", response_model=ClassReportResponse, dependencies=_WRITE_DEPS)
def editar_relatorio(
    report_id: UUID,
    data: ClassReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        # ✅ Soft delete: ignora relatórios arquivados
        report = db.query(ClassReport).filter(
            ClassReport.id == report_id,
            ClassReport.is_deleted == False,  # noqa: E712
        ).first()
        if not report:
            raise HTTPException(status_code=404, detail="Relatório não encontrado.")

        # v4: dono, status e reabertura de validado
        politicas.exigir(current_user, "relatorio_aula.editar", autor_id=report.created_by)
        status_anterior = report.status
        if status_anterior == estados.CANCELADO:
            raise HTTPException(status_code=400, detail="Relatório cancelado não pode ser editado.")
        reabrir = False
        if status_anterior == estados.VALIDADO:
            if not politicas.pode(current_user, "relatorio_aula.editar_validado"):
                raise HTTPException(
                    status_code=409,
                    detail="Este relatório já foi validado. Para alterar, peça à coordenação para devolvê-lo.",
                )
            reabrir = True
        chave_nome_antes = (report.turma_id, report.disciplina_id, report.data_aula, report.conteudo_ministrado)

        if data.professor_id:
            _validar_professor_disciplina(db, data.professor_id, data.disciplina_id)
        _validar_campos_condicionais(data)

        # v4 (restaurado de 19/08): na edição, rascunhos órfãos no slot não bloqueiam;
        # só relatórios já finalizados contam como duplicata.
        if data.horario_aula:
            data.horario_aula = _formatar_horario_canonico(data.horario_aula)
        turma_edit = db.query(Turma).filter(Turma.id == data.turma_id).first()
        disciplina_edit = db.query(Disciplina).filter(Disciplina.id == data.disciplina_id).first()
        nome_edit = _gerar_nome_ficheiro(turma_edit, disciplina_edit, data.data_aula, data.conteudo_ministrado)
        if nome_edit:
            _validar_ficheiro_duplicado(db, data.data_aula, nome_edit, exclude_report_id=report_id)
        _validar_slot_unico(
            db, data.turma_id, data.data_aula, data.horario_aula, data.disciplina_id,
            exclude_report_id=report_id, only_finalizados=True, tipo_aula=data.tipo_aula,
        )

        solicitante_antes = report.solicitante_antecipacao
        _aplicar_campos_do_payload(report, data.model_dump(), current_user)
        _conferir_pedido_seduc(db, report, solicitante_antes, current_user)

        # Data da gravação × data da aula na grade (reposição / antecipada) e o indicativo
        ajustar_datas_gravacao(report)
        _professor_da_exibicao(report)
        _aplicar_link_da_agenda(db, report)

        # Resolver horário pelo HORARIO_MAP se start_time não veio preenchido
        if not report.start_time and report.regular == "Sim" and report.horario_aula:
            turma_obj = db.query(Turma).filter(Turma.id == report.turma_id).first()
            nomenclatura = turma_obj.nomenclatura_padrao if turma_obj else ""
            st, et = _resolver_horario(
                report.horario_aula,
                nomenclatura,
                turno_usuario=report.turno or ""
            )
            if st and et:
                report.start_time = st
                report.end_time = et

        # v4 (restaurado de 19/08): na edição, rascunhos órfãos no slot não contam
        somente_finalizados = True

        # Verificar se o slot de horário excede o limite de relatórios permitidos
        _validar_duplicidade_limite_slot(
            db=db,
            turma_id=report.turma_id,
            data_aula=report.data_aula,
            horario_aula=report.horario_aula,
            regular=report.regular,
            start_time=report.start_time,
            exclude_report_id=report.id,
            tipo_aula=report.tipo_aula,
            only_finalizados=somente_finalizados,
        )

        nomenclatura_mudou = False
        chave_nome_depois = (report.turma_id, report.disciplina_id, report.data_aula, report.conteudo_ministrado)
        # v4: o nome do arquivo só é refeito quando a própria edição mexe em turma,
        # disciplina, data ou conteúdo. Renomear a turma no cadastro não muda mais o
        # nome de aulas já finalizadas (antes, qualquer edição posterior renomeava e
        # o vídeo e o PDF "sumiam").
        if report.status in STATUS_FINALIZADOS and (
            chave_nome_antes != chave_nome_depois or not report.nome_ficheiro_gerado
        ):
            turma = db.query(Turma).filter(Turma.id == report.turma_id).first()
            disciplina = db.query(Disciplina).filter(Disciplina.id == report.disciplina_id).first()
            try:
                nome_gerado = gerar_nome_padronizado(
                    nomenclatura_turma=turma.nomenclatura_padrao or turma.nome,
                    disciplina=disciplina.nome if disciplina else "",
                    data_aula=report.data_aula,
                    conteudo=report.conteudo_ministrado,
                    modalidade=turma.modalidade,
                )
            except ValueError as erro_nome:
                raise HTTPException(status_code=400, detail=str(erro_nome))
            # AP-006: só reprocessa (descarta links + reseta compliance + redispara
            # Celery) quando o nome do arquivo realmente muda, ou seja, quando algum
            # campo que afeta a nomenclatura (turma/disciplina/data/conteúdo) é
            # alterado. Edições de campos irrelevantes preservam os vínculos.
            nomenclatura_mudou = report.nome_ficheiro_gerado != nome_gerado
            report.nome_ficheiro_gerado = nome_gerado
            report.nome_normalizado = normalizar_para_match(nome_gerado)
            if nomenclatura_mudou:
                report.video_link = None
                report.slide_link = None
                report.md5_checksum = None
                report.status_compliance = "Pendente"

        # Validações de conflito e grade aplicam-se APENAS a relatórios já finalizados
        # (inclui a fila de validação da Coordenação e relatórios já validados)
        if report.status in STATUS_FINALIZADOS:
            # Validar slot da grade para aulas regulares na edição — Pula para tipos especiais (BUGFIX)
            if report.tipo_aula not in TIPOS_ESPECIAIS:
                _validar_slot_grade(
                    db,
                    report.turma_id,
                    report.data_aula,
                    report.disciplina_id,
                    report.horario_aula,
                    report.regular,
                    start_time=report.start_time,
                )

            # Verificar choque de horário na edição (igual à finalização) — Pula para tipos especiais (BUGFIX)
            if report.start_time and report.end_time and report.tipo_aula not in TIPOS_ESPECIAIS:
                _verificar_choque_horario(
                    db,
                    report.data_aula,
                    report.estudio,
                    report.start_time,
                    report.end_time,
                    exclude_id=report.id,
                    canal_utilizado=report.canal_utilizado,
                    # v4: antes comparava com "Gravação", valor que não existe no enum;
            # os tipos de gravação já pulam este bloco (TIPOS_ESPECIAIS).
            is_gravacao=False,
                    turma_id=report.turma_id,
                    tipo_aula=report.tipo_aula,
                )

        if reabrir:
            # Validado editado pela coordenação volta para a fila (precisa validar de novo)
            report.status = estados.destino("reabrir", status_anterior)
            report.validado_por = None
            report.validado_em = None

        log = AuditLog(
            actor_id=current_user.id,
            action="EDIT_REPORT",
            details=f"O utilizador {current_user.email} editou o relatório {report.id}"
            + (" (era VALIDADO: voltou para a fila de validação)" if reabrir else ""),
        )
        db.add(log)
        vincular_image_director_ao_class_report(db, report)
        registrar_versao(
            db, TIPO_AULA, report, "REABERTO" if reabrir else "EDITADO", current_user,
            status_anterior=status_anterior,
        )
        db.commit()
        db.refresh(report)

        # Dispara compliance task apenas quando a nomenclatura mudou (AP-006):
        # rebuscar links no Drive só faz sentido se o nome do arquivo mudou.
        if report.status in STATUS_FINALIZADOS and nomenclatura_mudou:
            try:
                from app.services.tarefas import agendar_verificacao
                agendar_verificacao(report.id, report.nome_ficheiro_gerado)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"Não foi possível disparar verificação de compliance na edição: {e}"
                )

        # TASK 06: Broadcast WebSocket
        _broadcast_report_update("EDITED", str(report.id), current_user.full_name)

        return report

    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as ie:
        db.rollback()
        if "uq_class_report_turma_data_horario" in str(ie.orig):
            raise HTTPException(
                status_code=409,
                detail="Não foi possível salvar o relatório. Já existe um relatório ativo (ou rascunho) registrado para esta Turma, Data, Horário e Disciplina.",
            )
        raise HTTPException(status_code=400, detail="Erro de integridade ao salvar registro.")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Erro Crítico em editar_relatorio: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro interno ao editar o relatório. A alteração não foi salva; tente de novo e, se continuar, avise o suporte.")


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_WRITE_DEPS)
def excluir_relatorio(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft delete: arquiva o relatório sem remover do banco. Acessível ao criador ou Admin (TASK 17)."""
    # ✅ Soft delete: ignora relatórios já arquivados
    report = db.query(ClassReport).filter(
        ClassReport.id == report_id,
        ClassReport.is_deleted == False,  # noqa: E712
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")

    # TASK 17: RBAC — Admin pode excluir qualquer; demais só os próprios
    if current_user.role != "admin" and report.created_by != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para excluir este relatório. Apenas o criador ou Admin pode excluir."
        )
    # v4: relatório que já entrou na fila (ou foi validado) não some da cobrança por
    # exclusão do autor; o caminho é cancelar com justificativa.
    if current_user.role != "admin" and report.status != estados.RASCUNHO:
        raise HTTPException(
            status_code=409,
            detail="Só rascunhos podem ser excluídos. Para um relatório finalizado, use Cancelar com justificativa.",
        )
    registrar_versao(db, TIPO_AULA, report, "EXCLUIDO", current_user, status_anterior=report.status)

    log = AuditLog(
        actor_id=current_user.id,
        action="DELETE_REPORT",
        details=f"{current_user.full_name} arquivou (soft delete) o relatório {report.id} (Turma: {report.turma_id}, Data: {report.data_aula})"
    )
    db.add(log)
    # ✅ Soft delete: marca como arquivado em vez de remover fisicamente
    report.is_deleted = True
    db.commit()

    # Broadcast WebSocket
    _broadcast_report_update("DELETED", str(report_id), current_user.full_name)

    return None
