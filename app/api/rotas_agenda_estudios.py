"""
Agenda de Estúdios — Admin e Diretor-Chefe editam; pedagógico (coordenador,
gestor, auditor) e diretores de imagem só visualizam.

Substitui a "PLANILHA AGENDAMENTO ESTÚDIOS": a grade das turmas vira a base de
cada dia e aqui se configura o que a grade não tem (diretor de cada estúdio,
agendamentos extras, cancelamentos, remanejamentos, feriados).
"""

import json
from datetime import date, datetime, time, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_role
from app.core.database import get_db
from app.models.agenda_estudio import (
    AgendamentoEstudio, BloqueioEstudio, ConfigEstudioAgenda, EscalaDiaEstudio,
    FeriadoAgenda, IntervaloAgenda, ObservacaoAgenda,
)
from app.models.auxiliares import Grade
from app.models.diretor_imagem import DiretorImagem
from app.models.infraestrutura import CanalIptvModel, Estudio
from app.models.turma import Turma
from app.models.user import User
from app.services import agenda_estudios as svc
from app.services.agenda_export import exportar_periodo

router = APIRouter(prefix="/api/v1/agenda-estudios", tags=["Agenda de Estúdios"])

PAPEIS_AGENDA = ("admin", "diretor_chefe")
# Só visualizam: pedagógico (coordenador, gestor, auditor) e diretores de imagem
# Pedagógico e auditoria consultam a disponibilidade. Diretor de imagem não: continua com a
# mesma grade do assistente; a visão consolidada por estúdio é do diretor-chefe.
PAPEIS_VISUALIZAR = PAPEIS_AGENDA + ("gestor", "coordenador", "auditor")
pode_agenda = require_role(*PAPEIS_AGENDA)
pode_ver = require_role(*PAPEIS_VISUALIZAR)

TURNOS_VALIDOS = {t[0] for t in svc.TURNOS}
MAX_DIAS_EXPORTACAO = 62


# ─── Schemas ──────────────────────────────────────────────────────────

class AgendamentoIn(BaseModel):
    data: date
    estudio_id: int
    horario_inicio: str
    horario_fim: str
    tipo: str
    titulo: str = Field(..., min_length=1, max_length=255)
    descricao: Optional[str] = None
    professor: Optional[str] = Field(None, max_length=255)
    turma_id: Optional[UUID] = None
    chamado: Optional[str] = Field(None, max_length=50)
    chamado_link: Optional[str] = Field(None, max_length=500)
    canal_iptv_id: Optional[int] = None
    departamento: Optional[str] = Field(None, max_length=120)
    # v3.5 — demandas outubro 2026 (eventos, chave, antecipação e mês de referência)
    chave_transmissao: Optional[str] = Field(None, max_length=255)
    nome_evento: Optional[str] = Field(None, max_length=255)
    responsavel_evento: Optional[str] = Field(None, max_length=255)
    solicitante_antecipacao: Optional[str] = Field(None, max_length=20)
    data_referencia: Optional[date] = None
    motivo_referencia: Optional[str] = Field(None, max_length=255)
    # Gravação ligada a uma aula da grade (na data_referencia): a que vai ao ar com ela
    # (antecipada) ou, com reposicao=True, a aula que não aconteceu e é reposta
    grade_exibicao_id: Optional[UUID] = None
    reposicao: bool = False
    # Aulas da grade que estão no horário: para onde cada uma vai neste dia
    # (estudio_id vazio = cancelar a aula neste dia). Nenhuma aula fica sem destino.
    remanejar_aulas: List["RemanejoAulaIn"] = Field(default_factory=list)
    # Legado: cancela todas as aulas do horário que não estiverem em remanejar_aulas
    cancelar_aulas_conflitantes: bool = False
    # Ciente dos avisos (professor/turma ocupados, relatório já registrado) e agenda assim mesmo
    confirmar_avisos: bool = False


class RemanejoAulaIn(BaseModel):
    grade_id: UUID
    estudio_id: Optional[int] = None  # None = cancelar a aula neste dia
    canal_iptv_id: Optional[int] = None


AgendamentoIn.model_rebuild()


class FeriadoIn(BaseModel):
    data: date
    nome: str = Field(..., min_length=1, max_length=120)


class ObservacaoIn(BaseModel):
    data: date
    grade_id: Optional[UUID] = None
    agendamento_id: Optional[UUID] = None
    texto: str = Field(..., min_length=1, max_length=2000)
    link: Optional[str] = Field(None, max_length=500)


class ConfigEstudioIn(BaseModel):
    libras: bool = False
    prioridade_evento: Optional[int] = Field(None, ge=1, le=99)


class EstudioFixoIn(BaseModel):
    grade_id: UUID
    estudio_id: int


class StatusIn(BaseModel):
    status: str


class CancelarAulaIn(BaseModel):
    data: date
    grade_id: UUID
    motivo: Optional[str] = None
    chamado: Optional[str] = Field(None, max_length=50)
    chamado_link: Optional[str] = Field(None, max_length=500)


class RemanejarAulaIn(BaseModel):
    data: date
    grade_id: UUID
    estudio_destino_id: int
    canal_iptv_id: Optional[int] = None
    motivo: Optional[str] = None
    chamado: Optional[str] = Field(None, max_length=50)
    chamado_link: Optional[str] = Field(None, max_length=500)
    confirmar_avisos: bool = False
    # Só gravação da grade (MP): outro horário neste dia (arrastar na vertical)
    horario_inicio: Optional[time] = None
    horario_fim: Optional[time] = None


class BloqueioIn(BaseModel):
    estudio_id: int
    dias_semana: List[int]
    horario_inicio: str
    horario_fim: str
    motivo: Optional[str] = Field(None, max_length=255)
    ativo: bool = True
    tipo: str = "TRANCADO"            # TRANCADO | SOB_DEMANDA
    minimo_aulas: Optional[int] = Field(None, ge=1, le=20)


class IntervaloIn(BaseModel):
    turno: str                                   # manha | tarde
    estudio_id: Optional[int] = None             # vazio = padrão de todos os estúdios
    horario_inicio: Optional[str] = None         # vazio: padrão = sem intervalo; estúdio = segue o padrão
    horario_fim: Optional[str] = None
    a_partir_de: date
    so_neste_dia: bool = False
    motivo: Optional[str] = Field(None, max_length=255)


class CopiarEscalaDiaIn(BaseModel):
    de_data: date
    para_datas: List[date] = Field(..., min_length=1, max_length=62)


class TrocaIn(BaseModel):
    diretor_imagem_id: UUID
    a_partir: Optional[str] = None   # HH:MM em que este diretor assume


MAX_TROCAS = 6


class EscalaDiaIn(BaseModel):
    data: date
    turno: str
    estudio_id: int
    diretor_imagem_id: Optional[UUID] = None  # None = sem diretor neste dia
    observacao: Optional[str] = Field(None, max_length=255)
    # Segundo diretor no mesmo estúdio e turno (troca no meio do turno)
    diretor2_imagem_id: Optional[UUID] = None
    troca_horario: Optional[str] = None
    # Todos os diretores que assumem depois do primeiro, em ordem (substitui diretor2/troca_horario)
    trocas: Optional[List[TrocaIn]] = Field(None, max_length=MAX_TROCAS)
    # None = não mexe no link/chave já informados; "" = apaga
    youtube_link: Optional[str] = Field(None, max_length=500)
    chave_transmissao: Optional[str] = Field(None, max_length=255)


class TransmissaoItemIn(BaseModel):
    turno: str
    estudio_id: int
    youtube_link: Optional[str] = Field(None, max_length=500)
    chave_transmissao: Optional[str] = Field(None, max_length=255)


class TransmissaoDiaIn(BaseModel):
    data: date
    itens: List[TransmissaoItemIn] = Field(..., max_length=200)


# ─── Validações ───────────────────────────────────────────────────────

def _estudio_ativo(db: Session, estudio_id: int) -> Estudio:
    est = db.query(Estudio).filter(Estudio.id == estudio_id, Estudio.ativo == True).first()  # noqa: E712
    if not est:
        raise HTTPException(422, "Estúdio inativo ou não encontrado.")
    return est


def _sem_feriado(db: Session, data: date) -> None:
    f = svc.feriado_do_dia(db, data)
    if f:
        raise HTTPException(422, f"{data.strftime('%d/%m/%Y')} está marcado como feriado ({f.nome}): "
                                 "a agenda desse dia fica trancada.")


def _turno_valido(turno: str) -> str:
    t = (turno or "").strip().lower()
    if t not in TURNOS_VALIDOS:
        raise HTTPException(422, "Turno inválido. Use manha, tarde ou noite.")
    return t


def _diretor_ativo(db: Session, diretor_id: Optional[UUID]) -> None:
    if diretor_id is None:
        return
    ok = db.query(DiretorImagem).filter(
        DiretorImagem.id == diretor_id, DiretorImagem.is_active == True  # noqa: E712
    ).first()
    if not ok:
        raise HTTPException(422, "Diretor de imagem inativo ou não encontrado.")


def _canal_valido(db: Session, canal_id: Optional[int]) -> None:
    if canal_id is not None and not db.query(CanalIptvModel).filter(CanalIptvModel.id == canal_id).first():
        raise HTTPException(422, "Canal não encontrado.")


def _horarios(inicio: str, fim: str):
    try:
        h_ini, h_fim = svc.parse_hora(inicio), svc.parse_hora(fim)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if h_fim <= h_ini:
        raise HTTPException(422, "O horário final deve ser depois do inicial.")
    return h_ini, h_fim


def _validar_solicitacao(dados: AgendamentoIn) -> None:
    """
    Reuniões de out/2026: o diretor-chefe descreve cada uso do estúdio na Agenda.
    - Caixa SEDUC em todo agendamento: marcada = pedido da SEDUC (nº do chamado obrigatório).
    - Gravação + SEDUC ligada à aula da grade (data posterior) = aula antecipada SEDUC:
      cobra a gravação e a exibição. Sem SEDUC, cobra só a exibição.
    - Gravação marcada como Reposição: a data de referência é a aula que não aconteceu
      (anterior à gravação), opcionalmente ligada à aula da grade daquele dia.
    """
    sol = (dados.solicitante_antecipacao or "").strip().upper() or None
    if sol not in (None, "SEDUC", "PROFESSOR"):
        raise HTTPException(422, "Solicitação inválida: use SEDUC ou PROFESSOR (Canal Educação).")
    dados.solicitante_antecipacao = sol
    if sol == "SEDUC" and not (dados.chamado or "").strip().lstrip("#"):
        raise HTTPException(422, "Solicitação da SEDUC: informe o nº do chamado.")
    if dados.tipo not in svc.TIPOS_GRAVACAO:
        dados.reposicao = False
        dados.data_referencia = None
        dados.grade_exibicao_id = None
        return
    if dados.reposicao:
        if not dados.data_referencia:
            raise HTTPException(422, "Reposição: informe a data da aula que não aconteceu.")
        if dados.data_referencia >= dados.data:
            raise HTTPException(422, "Reposição: a data da aula que não aconteceu precisa ser antes do dia da gravação.")
    elif dados.data_referencia and dados.data_referencia <= dados.data:
        raise HTTPException(422, "Gravação antecipada: a data da exibição precisa ser depois do dia da gravação.")
    if dados.grade_exibicao_id and not dados.data_referencia:
        raise HTTPException(422, "Informe a data da aula da grade ligada a esta gravação.")


def _aula_exibida_valida(db: Session, dados: AgendamentoIn) -> None:
    """A aula escolhida para a exibição precisa estar na grade da turma naquela data."""
    if not dados.grade_exibicao_id:
        return
    if not dados.turma_id:
        raise HTTPException(422, "Escolha a turma para ligar a gravação à aula da grade.")
    ids = {a["grade_id"] for a in svc.aulas_da_turma_no_dia(db, dados.turma_id, dados.data_referencia)}
    if str(dados.grade_exibicao_id) not in ids:
        raise HTTPException(422, "A aula escolhida não está na grade da turma na data da exibição.")


def _validar_agendamento(db: Session, dados: AgendamentoIn, ignorar_id: Optional[UUID] = None):
    """
    Checa tudo o que já existe no sistema antes de gravar a reserva:
    1. feriado, estúdio ativo e dentro do horário de funcionamento (bloqueia);
    2. outro agendamento no mesmo estúdio/horário (bloqueia);
    3. aula da grade no mesmo estúdio/horário: cada aula precisa de um destino
       (outro estúdio livre) ou ser cancelada no dia — nenhuma fica sem estúdio;
    4. professor/turma ocupados em outro estúdio, horário trancado ou sob demanda,
       relatório de aula já registrado (pede confirmação).
    """
    if dados.tipo not in svc.TIPOS_AGENDAMENTO:
        raise HTTPException(422, "Tipo de agendamento inválido.")
    _validar_solicitacao(dados)
    if dados.tipo == "EVENTO":
        if not (dados.nome_evento and dados.nome_evento.strip()):
            if dados.titulo and dados.titulo.strip():
                dados.nome_evento = dados.titulo.strip()
            else:
                raise HTTPException(422, "O Nome do Evento é obrigatório quando o tipo for Evento.")
        elif not (dados.titulo and dados.titulo.strip()):
            dados.titulo = dados.nome_evento.strip()
    _sem_feriado(db, dados.data)
    est = _estudio_ativo(db, dados.estudio_id)
    if dados.turma_id and not db.query(Turma).filter(Turma.id == dados.turma_id).first():
        raise HTTPException(422, "Turma não encontrada.")
    _canal_valido(db, dados.canal_iptv_id)
    _aula_exibida_valida(db, dados)
    h_ini, h_fim = _horarios(dados.horario_inicio, dados.horario_fim)
    if svc.fora_do_funcionamento(est, h_ini, h_fim):
        raise HTTPException(
            422,
            f"{est.nome} funciona das {svc.hm(est.horario_inicio)} às {svc.hm(est.horario_fim)}. "
            "Ajuste o horário ou o cadastro do estúdio em Configurações.",
        )

    c = svc.conflitos(db, dados.data, dados.estudio_id, h_ini, h_fim, ignorar_id)
    if c["agendamentos"]:
        raise HTTPException(409, {
            "tipo": "agendamento",
            "message": "Já existe agendamento nesse estúdio e horário: "
                       + "; ".join(svc.descrever_agendamento(a) for a in c["agendamentos"]),
        })
    avisos = svc.avisos_agendamento(
        db, dados.data, dados.estudio_id, h_ini, h_fim, dados.professor, dados.turma_id, ignorar_id,
    )
    decisoes = {str(r.grade_id): r for r in dados.remanejar_aulas}
    pendentes = [s for s in c["aulas"] if s["grade_id"] not in decisoes and not dados.cancelar_aulas_conflitantes]
    precisa_ciencia = bool(avisos) and not dados.confirmar_avisos
    if pendentes or precisa_ciencia:
        ocupado_pelo_agendamento = {dados.estudio_id: [(h_ini, h_fim)]}
        raise HTTPException(409, {
            "tipo": "confirmar",
            "message": "Confira o que já está cadastrado nesse horário antes de agendar.",
            "aulas": [svc.descrever_aula(s) for s in c["aulas"]],
            "aulas_detalhe": [{
                "grade_id": s["grade_id"],
                "descricao": svc.descrever_aula(s),
                "inicio": svc.hm(s["inicio"]),
                "fim": svc.hm(s["fim"]),
                "sugestoes": svc.sugerir_estudios(
                    db, dados.data, s["inicio"], s["fim"], para="aula",
                    ignorar_grade_id=s["grade_id"], ignorar_agendamento_id=ignorar_id,
                    ocupados_extra=ocupado_pelo_agendamento,
                ),
            } for s in c["aulas"]],
            "avisos": avisos,
        })

    # Destinos escolhidos: estúdio ativo, funcionando, livre e sem choque entre si
    plano = []
    usados: dict = {dados.estudio_id: [(h_ini, h_fim)]}
    for s in c["aulas"]:
        d = decisoes.get(s["grade_id"])
        destino_id = d.estudio_id if d else None
        if destino_id is None:
            plano.append((s, None, None))
            continue
        destino = _estudio_ativo(db, destino_id)
        _canal_valido(db, d.canal_iptv_id)
        if svc.fora_do_funcionamento(destino, s["inicio"], s["fim"]):
            raise HTTPException(409, {"tipo": "remanejo", "message": f"{destino.nome} não funciona no horário de "
                                      f"{svc.descrever_aula(s)}."})
        cc = svc.conflitos(db, dados.data, destino.id, s["inicio"], s["fim"],
                           ignorar_id, ignorar_grade_id=s["grade_id"])
        # o que está saindo do destino para dar lugar não conta como ocupação
        cc_aulas = [x for x in cc["aulas"] if x["grade_id"] not in decisoes]
        if cc_aulas or cc["agendamentos"] or any(
            svc.sobrepoe(s["inicio"], s["fim"], a, b) for a, b in usados.get(destino.id, [])
        ):
            raise HTTPException(409, {"tipo": "remanejo", "message": f"{destino.nome} não está livre para "
                                      f"{svc.descrever_aula(s)}. Escolha outro estúdio."})
        usados.setdefault(destino.id, []).append((s["inicio"], s["fim"]))
        plano.append((s, destino, d.canal_iptv_id))
    return h_ini, h_fim, plano


def _definir_ocorrencia(
    db: Session, data: date, slot: dict, tipo: str, estudio_id: int, user: User, *,
    descricao: Optional[str] = None, chamado: Optional[str] = None, chamado_link: Optional[str] = None,
    canal_iptv_id: Optional[int] = None, horario: Optional[tuple] = None,
) -> AgendamentoEstudio:
    """Cancelamento ou remanejamento da aula no dia — substitui o que já houver para ela."""
    existente = db.query(AgendamentoEstudio).filter(
        AgendamentoEstudio.data == data,
        AgendamentoEstudio.grade_id == UUID(slot["grade_id"]),
        AgendamentoEstudio.tipo.in_(svc.OCORRENCIAS_DE_AULA),
    ).first()
    o = existente or AgendamentoEstudio(data=data, grade_id=UUID(slot["grade_id"]), criado_por=user.id)
    o.tipo = tipo
    o.estudio_id = estudio_id
    o.horario_inicio = horario[0] if horario else slot.get("inicio_grade", slot["inicio"])
    o.horario_fim = horario[1] if horario else slot.get("fim_grade", slot["fim"])
    o.titulo = slot["disciplina"] or "Aula"
    o.turma_id = UUID(slot["turma_id"])
    o.descricao = (descricao or "").strip() or None
    o.chamado = (chamado or "").strip().lstrip("#") or None
    o.chamado_link = (chamado_link or "").strip() or None
    o.canal_iptv_id = canal_iptv_id
    o.status = svc.STATUS_AGENDADO
    o.atualizado_por = user.id
    if not existente:
        db.add(o)
    return o


def _aplicar_plano(db: Session, data: date, plano: list, agendamento: AgendamentoEstudio, user: User):
    """Cancela ou remaneja as aulas que estavam no horário do agendamento. Devolve (canceladas, remanejadas)."""
    canceladas = remanejadas = 0
    for s, destino, canal_id in plano:
        motivo = f"Estúdio usado por: {agendamento.titulo}"
        if destino is None:
            _definir_ocorrencia(db, data, s, svc.AULA_CANCELADA, s["estudio_efetivo"], user, descricao=motivo,
                                chamado=agendamento.chamado, chamado_link=agendamento.chamado_link)
            canceladas += 1
        elif destino.id == s["estudio_id"]:
            # volta para o estúdio da grade: desfaz o remanejamento do dia
            db.query(AgendamentoEstudio).filter(
                AgendamentoEstudio.data == data, AgendamentoEstudio.grade_id == UUID(s["grade_id"]),
                AgendamentoEstudio.tipo.in_(svc.OCORRENCIAS_DE_AULA),
            ).delete(synchronize_session=False)
            remanejadas += 1
        else:
            _definir_ocorrencia(db, data, s, svc.AULA_REMANEJADA, destino.id, user, descricao=motivo,
                                chamado=agendamento.chamado, chamado_link=agendamento.chamado_link,
                                canal_iptv_id=canal_id)
            remanejadas += 1
    return canceladas, remanejadas


def _aula_prevista(db: Session, data: date, grade_id: UUID) -> dict:
    for s in svc.aulas_do_dia(db, data):
        if s["grade_id"] == str(grade_id):
            if s["gravacao_sem_horario"]:
                raise HTTPException(422, "Gravação sem horário definido na grade não entra na agenda.")
            return s
    raise HTTPException(404, "Essa aula não está prevista na grade nesse dia.")


def _get_agendamento(db: Session, agendamento_id: UUID) -> AgendamentoEstudio:
    a = db.query(AgendamentoEstudio).filter(AgendamentoEstudio.id == agendamento_id).first()
    if not a:
        raise HTTPException(404, "Agendamento não encontrado.")
    return a


# ─── Consulta ─────────────────────────────────────────────────────────

@router.get("/opcoes")
def listar_opcoes(db: Session = Depends(get_db), user: User = Depends(pode_ver)):
    return {**svc.opcoes(db), "pode_editar": user.role in PAPEIS_AGENDA}


@router.get("/dia")
def agenda_do_dia(
    data: date = Query(default_factory=date.today),
    db: Session = Depends(get_db),
    user: User = Depends(pode_ver),
):
    agenda = svc.montar_agenda_dia(db, data)
    if user.role not in PAPEIS_AGENDA:  # link e chave de transmissão: só quem edita e o diretor escalado
        for t in agenda["turnos"]:
            for c in t["estudios"]:
                if c.get("diretor"):
                    c["diretor"].pop("youtube_link", None)
                    c["diretor"].pop("chave_transmissao", None)
                c.pop("transmissao", None)
    return agenda


@router.get("/agendamentos")
def listar_agendamentos(
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    estudio_id: Optional[int] = Query(None),
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    busca: Optional[str] = Query(None, description="Título, professor ou nº do chamado"),
    db: Session = Depends(get_db),
    _: User = Depends(pode_ver),
):
    inicio = data_inicio or date.today()
    fim = data_fim or (inicio + timedelta(days=30))
    if inicio > fim:
        raise HTTPException(422, "A data de início não pode ser maior que a data de fim.")
    q = db.query(AgendamentoEstudio).filter(
        AgendamentoEstudio.data >= inicio, AgendamentoEstudio.data <= fim,
    )
    if estudio_id:
        q = q.filter(AgendamentoEstudio.estudio_id == estudio_id)
    if tipo:
        q = q.filter(AgendamentoEstudio.tipo == tipo)
    if status:
        q = q.filter(AgendamentoEstudio.status == status)
    if busca:
        termo = f"%{busca.strip()}%"
        q = q.filter(
            AgendamentoEstudio.titulo.ilike(termo)
            | AgendamentoEstudio.professor.ilike(termo)
            | AgendamentoEstudio.chamado.ilike(termo)
        )
    itens = q.order_by(AgendamentoEstudio.data, AgendamentoEstudio.horario_inicio).all()
    return {
        "data_inicio": inicio.isoformat(),
        "data_fim": fim.isoformat(),
        "total": len(itens),
        "items": [svc.agendamento_to_dict(a) for a in itens],
    }


# ─── Agendamentos ─────────────────────────────────────────────────────

@router.post("/agendamentos", status_code=201)
def criar_agendamento(
    dados: AgendamentoIn,
    db: Session = Depends(get_db),
    user: User = Depends(pode_agenda),
):
    h_ini, h_fim, plano = _validar_agendamento(db, dados)
    a = AgendamentoEstudio(
        data=dados.data, estudio_id=dados.estudio_id, horario_inicio=h_ini, horario_fim=h_fim,
        tipo=dados.tipo, titulo=dados.titulo.strip(), descricao=dados.descricao,
        professor=(dados.professor or "").strip() or None, turma_id=dados.turma_id,
        chamado=(dados.chamado or "").strip().lstrip("#") or None,
        chamado_link=(dados.chamado_link or "").strip() or None,
        canal_iptv_id=dados.canal_iptv_id,
        departamento=(dados.departamento or "").strip() or None,
        chave_transmissao=(dados.chave_transmissao or "").strip() or None,
        nome_evento=(dados.nome_evento or "").strip() or None,
        responsavel_evento=(dados.responsavel_evento or "").strip() or None,
        solicitante_antecipacao=(dados.solicitante_antecipacao or "").strip() or None,
        data_referencia=dados.data_referencia,
        motivo_referencia=(dados.motivo_referencia or "").strip() or None,
        grade_exibicao_id=dados.grade_exibicao_id,
        reposicao=bool(dados.reposicao),
        status=svc.STATUS_AGENDADO, criado_por=user.id, atualizado_por=user.id,
    )
    db.add(a)
    canceladas, remanejadas = _aplicar_plano(db, dados.data, plano, a, user)
    db.commit()
    db.refresh(a)
    return {**svc.agendamento_to_dict(a), "aulas_canceladas": canceladas, "aulas_remanejadas": remanejadas}


@router.put("/agendamentos/{agendamento_id}")
def editar_agendamento(
    agendamento_id: UUID,
    dados: AgendamentoIn,
    db: Session = Depends(get_db),
    user: User = Depends(pode_agenda),
):
    a = _get_agendamento(db, agendamento_id)
    if a.tipo in svc.OCORRENCIAS_DE_AULA:
        raise HTTPException(422, "Cancelamento/remanejamento de aula não se edita aqui; restaure a aula se precisar.")
    if a.status == svc.STATUS_CANCELADO:
        # Cancelado não ocupa o estúdio: edita sem checar conflito de horário
        if dados.tipo not in svc.TIPOS_AGENDAMENTO:
            raise HTTPException(422, "Tipo de agendamento inválido.")
        _validar_solicitacao(dados)
        _estudio_ativo(db, dados.estudio_id)
        h_ini, h_fim = _horarios(dados.horario_inicio, dados.horario_fim)
        plano = []
    else:
        h_ini, h_fim, plano = _validar_agendamento(db, dados, ignorar_id=a.id)
    a.data, a.estudio_id, a.horario_inicio, a.horario_fim = dados.data, dados.estudio_id, h_ini, h_fim
    a.tipo, a.titulo, a.descricao = dados.tipo, dados.titulo.strip(), dados.descricao
    a.professor = (dados.professor or "").strip() or None
    a.turma_id = dados.turma_id
    a.chamado = (dados.chamado or "").strip().lstrip("#") or None
    a.chamado_link = (dados.chamado_link or "").strip() or None
    a.canal_iptv_id = dados.canal_iptv_id
    a.departamento = (dados.departamento or "").strip() or None
    a.chave_transmissao = (dados.chave_transmissao or "").strip() or None
    a.nome_evento = (dados.nome_evento or "").strip() or None
    a.responsavel_evento = (dados.responsavel_evento or "").strip() or None
    a.solicitante_antecipacao = (dados.solicitante_antecipacao or "").strip() or None
    a.data_referencia = dados.data_referencia
    a.motivo_referencia = (dados.motivo_referencia or "").strip() or None
    a.grade_exibicao_id = dados.grade_exibicao_id
    a.reposicao = bool(dados.reposicao)
    a.atualizado_por = user.id
    canceladas, remanejadas = _aplicar_plano(db, dados.data, plano, a, user)
    db.commit()
    db.refresh(a)
    return {**svc.agendamento_to_dict(a), "aulas_canceladas": canceladas, "aulas_remanejadas": remanejadas}


@router.patch("/agendamentos/{agendamento_id}/status")
def mudar_status_agendamento(
    agendamento_id: UUID,
    dados: StatusIn,
    db: Session = Depends(get_db),
    user: User = Depends(pode_agenda),
):
    a = _get_agendamento(db, agendamento_id)
    novo = (dados.status or "").upper()
    if novo not in (svc.STATUS_AGENDADO, svc.STATUS_CANCELADO):
        raise HTTPException(422, "Status inválido. Use AGENDADO ou CANCELADO.")
    if a.tipo in svc.OCORRENCIAS_DE_AULA:
        raise HTTPException(422, "Para desfazer o cancelamento/remanejamento de uma aula use 'Restaurar aula'.")
    _sem_feriado(db, a.data)
    if novo == svc.STATUS_AGENDADO and a.status != novo:
        c = svc.conflitos(db, a.data, a.estudio_id, a.horario_inicio, a.horario_fim, a.id)
        if c["agendamentos"] or c["aulas"]:
            ocupantes = [svc.descrever_agendamento(x) for x in c["agendamentos"]] + [
                svc.descrever_aula(s) for s in c["aulas"]
            ]
            raise HTTPException(409, "Não dá para reativar: o horário já está ocupado — " + "; ".join(ocupantes))
    a.status = novo
    a.atualizado_por = user.id
    db.commit()
    db.refresh(a)
    return svc.agendamento_to_dict(a)


@router.delete("/agendamentos/{agendamento_id}", status_code=204)
def excluir_agendamento(
    agendamento_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(pode_agenda),
):
    a = _get_agendamento(db, agendamento_id)
    db.delete(a)
    db.commit()


# ─── Aulas da grade: cancelar / restaurar num dia ─────────────────────

@router.post("/aulas/cancelar", status_code=201)
def cancelar_aula(
    dados: CancelarAulaIn,
    db: Session = Depends(get_db),
    user: User = Depends(pode_agenda),
):
    _sem_feriado(db, dados.data)
    slot = _aula_prevista(db, dados.data, dados.grade_id)
    o = _definir_ocorrencia(
        db, dados.data, slot, svc.AULA_CANCELADA, slot["estudio_efetivo"] or slot["estudio_id"], user,
        descricao=dados.motivo, chamado=dados.chamado, chamado_link=dados.chamado_link,
    )
    db.commit()
    db.refresh(o)
    return svc.agendamento_to_dict(o)


@router.post("/aulas/remanejar", status_code=201)
def remanejar_aula(
    dados: RemanejarAulaIn,
    db: Session = Depends(get_db),
    user: User = Depends(pode_agenda),
):
    """
    Leva a aula para outro estúdio só neste dia (ex.: manutenção). A grade não muda.
    Aula da grade só troca de estúdio; GRAVAÇÃO da grade (MP) também pode mudar de
    horário no dia (reunião 26/10/2026 — arrastar na vertical).
    """
    _sem_feriado(db, dados.data)
    slot = _aula_prevista(db, dados.data, dados.grade_id)
    destino = _estudio_ativo(db, dados.estudio_destino_id)
    _canal_valido(db, dados.canal_iptv_id)
    horario = None
    if dados.horario_inicio or dados.horario_fim:
        if not (dados.horario_inicio and dados.horario_fim):
            raise HTTPException(422, "Informe o início e o fim do novo horário.")
        if dados.horario_fim <= dados.horario_inicio:
            raise HTTPException(422, "O fim precisa ser depois do início.")
        if (dados.horario_inicio, dados.horario_fim) != (slot["inicio_grade"], slot["fim_grade"]):
            if slot.get("tipo_slot") != "gravacao":
                raise HTTPException(422, "Só gravação da grade muda de horário no dia; aula da grade só troca de estúdio.")
            horario = (dados.horario_inicio, dados.horario_fim)
    if destino.id == slot["estudio_id"] and horario is None:
        raise HTTPException(422, "Esse já é o estúdio da aula na grade — use 'Restaurar aula' para voltar.")
    ini_dia, fim_dia = horario or (slot["inicio_grade"], slot["fim_grade"])
    slot = {**slot, "inicio": ini_dia, "fim": fim_dia}
    if svc.fora_do_funcionamento(destino, slot["inicio"], slot["fim"]):
        raise HTTPException(422, f"{destino.nome} não funciona nesse horário "
                                 f"({svc.hm(destino.horario_inicio)}–{svc.hm(destino.horario_fim)}).")
    c = svc.conflitos(db, dados.data, destino.id, slot["inicio"], slot["fim"], ignorar_grade_id=slot["grade_id"])
    ocupantes = [svc.descrever_aula(x) for x in c["aulas"]] + [svc.descrever_agendamento(x) for x in c["agendamentos"]]
    if ocupantes:
        raise HTTPException(409, f"{destino.nome} está ocupado nesse horário: " + "; ".join(ocupantes))
    avisos = [
        f"Horário trancado no {destino.nome} das {svc.hm(b.horario_inicio)} às {svc.hm(b.horario_fim)}"
        f"{(': ' + b.motivo) if b.motivo else ''}."
        for b in svc.bloqueios_do_dia(db, dados.data).get(destino.id, [])
        if svc.sobrepoe(slot["inicio"], slot["fim"], b.horario_inicio, b.horario_fim)
    ]
    if avisos and not dados.confirmar_avisos:
        raise HTTPException(409, {"tipo": "confirmar", "message": "Confira antes de remanejar.",
                                  "aulas": [], "avisos": avisos})
    o = _definir_ocorrencia(
        db, dados.data, slot, svc.AULA_REMANEJADA, destino.id, user,
        descricao=dados.motivo, chamado=dados.chamado, chamado_link=dados.chamado_link,
        canal_iptv_id=dados.canal_iptv_id, horario=horario,
    )
    db.commit()
    db.refresh(o)
    return svc.agendamento_to_dict(o)


@router.post("/aulas/restaurar")
def restaurar_aula(
    dados: CancelarAulaIn,
    db: Session = Depends(get_db),
    _: User = Depends(pode_agenda),
):
    """Desfaz cancelamento ou remanejamento: a aula volta para o estúdio da grade."""
    _sem_feriado(db, dados.data)
    o = db.query(AgendamentoEstudio).filter(
        AgendamentoEstudio.data == dados.data,
        AgendamentoEstudio.grade_id == dados.grade_id,
        AgendamentoEstudio.tipo.in_(svc.OCORRENCIAS_DE_AULA),
    ).first()
    if not o:
        raise HTTPException(404, "Essa aula não está cancelada nem remanejada nesse dia.")
    g = db.query(Grade).filter(Grade.id == dados.grade_id).first()
    if g and g.estudio_id:
        c = svc.conflitos(db, o.data, g.estudio_id, g.horario_inicio or o.horario_inicio,
                          g.horario_fim or o.horario_fim, ignorar_grade_id=str(g.id))
        if c["agendamentos"] or c["aulas"]:
            ocupantes = [svc.descrever_agendamento(x) for x in c["agendamentos"]] + [
                svc.descrever_aula(x) for x in c["aulas"]
            ]
            raise HTTPException(
                409,
                "O estúdio da grade está ocupado nesse horário (" + "; ".join(ocupantes)
                + "). Cancele ou mova o que está lá antes de restaurar a aula.",
            )
    db.delete(o)
    db.commit()
    return {"ok": True}


# ─── Horários trancados ───────────────────────────────────────────────

@router.get("/bloqueios")
def listar_bloqueios(db: Session = Depends(get_db), _: User = Depends(pode_ver)):
    return [svc.bloqueio_to_dict(b) for b in db.query(BloqueioEstudio).order_by(
        BloqueioEstudio.estudio_id, BloqueioEstudio.horario_inicio).all()]


def _aplicar_bloqueio(db: Session, b: BloqueioEstudio, dados: BloqueioIn, user: User) -> None:
    _estudio_ativo(db, dados.estudio_id)
    dias = sorted({d for d in dados.dias_semana if 0 <= d <= 6})
    if not dias:
        raise HTTPException(422, "Escolha pelo menos um dia da semana.")
    h_ini, h_fim = _horarios(dados.horario_inicio, dados.horario_fim)
    b.estudio_id, b.horario_inicio, b.horario_fim = dados.estudio_id, h_ini, h_fim
    b.dias_semana = ",".join(str(d) for d in dias)
    b.motivo = (dados.motivo or "").strip() or None
    b.ativo = dados.ativo
    tipo = (dados.tipo or svc.BLOQUEIO_TRANCADO).upper()
    if tipo not in (svc.BLOQUEIO_TRANCADO, svc.BLOQUEIO_SOB_DEMANDA):
        raise HTTPException(422, "Tipo inválido. Use TRANCADO ou SOB_DEMANDA.")
    b.tipo = tipo
    b.minimo_aulas = (dados.minimo_aulas or svc.MINIMO_AULAS_SOB_DEMANDA) if tipo == svc.BLOQUEIO_SOB_DEMANDA else None
    b.atualizado_por = user.id
    b.atualizado_em = datetime.utcnow()


@router.post("/bloqueios", status_code=201)
def criar_bloqueio(dados: BloqueioIn, db: Session = Depends(get_db), user: User = Depends(pode_agenda)):
    b = BloqueioEstudio()
    _aplicar_bloqueio(db, b, dados, user)
    db.add(b)
    db.commit()
    db.refresh(b)
    return svc.bloqueio_to_dict(b)


@router.put("/bloqueios/{bloqueio_id}")
def editar_bloqueio(bloqueio_id: int, dados: BloqueioIn, db: Session = Depends(get_db),
                    user: User = Depends(pode_agenda)):
    b = db.query(BloqueioEstudio).filter(BloqueioEstudio.id == bloqueio_id).first()
    if not b:
        raise HTTPException(404, "Horário trancado não encontrado.")
    _aplicar_bloqueio(db, b, dados, user)
    db.commit()
    db.refresh(b)
    return svc.bloqueio_to_dict(b)


@router.delete("/bloqueios/{bloqueio_id}", status_code=204)
def excluir_bloqueio(bloqueio_id: int, db: Session = Depends(get_db), _: User = Depends(pode_agenda)):
    db.query(BloqueioEstudio).filter(BloqueioEstudio.id == bloqueio_id).delete(synchronize_session=False)
    db.commit()


# ─── Intervalos do turno ──────────────────────────────────────────────

@router.get("/intervalos")
def listar_intervalos(data: Optional[date] = Query(None), db: Session = Depends(get_db), _: User = Depends(pode_ver)):
    """O que vale no dia (padrão e cada estúdio) e o histórico de mudanças."""
    return {**svc.quadro_intervalos(db, data or date.today()), "historico": svc.historico_intervalos(db)}


@router.post("/intervalos", status_code=201)
def definir_intervalo(dados: IntervaloIn, db: Session = Depends(get_db), user: User = Depends(pode_agenda)):
    """
    Muda o intervalo do dia escolhido em diante (ou só nesse dia). Os dias que já passaram
    não mudam: cada mudança é uma nova versão, e a antiga continua valendo para trás.
    """
    if dados.turno not in svc.TURNOS_COM_INTERVALO:
        raise HTTPException(422, "Turno inválido. Use manhã ou tarde.")
    if dados.a_partir_de < date.today():
        raise HTTPException(422, "Dias que já passaram ficam com o intervalo que tinham. "
                                 "Escolha hoje ou um dia à frente.")
    if dados.estudio_id is not None:
        _estudio_ativo(db, dados.estudio_id)
    h_ini = h_fim = None
    if dados.horario_inicio or dados.horario_fim:
        if not (dados.horario_inicio and dados.horario_fim):
            raise HTTPException(422, "Informe o início e o fim do intervalo.")
        h_ini, h_fim = _horarios(dados.horario_inicio, dados.horario_fim)
        if svc.turno_do_horario(h_ini) != dados.turno:
            raise HTTPException(422, f"{svc.hm(h_ini)} não é horário do turno da {svc.TURNO_LABEL[dados.turno].lower()}.")
    ate = dados.a_partir_de if dados.so_neste_dia else None
    i = db.query(IntervaloAgenda).filter(
        IntervaloAgenda.turno == dados.turno,
        IntervaloAgenda.estudio_id.is_(None) if dados.estudio_id is None else IntervaloAgenda.estudio_id == dados.estudio_id,
        IntervaloAgenda.vigente_desde == dados.a_partir_de,
        IntervaloAgenda.vigente_ate.is_(None) if ate is None else IntervaloAgenda.vigente_ate == ate,
    ).first()
    if not i:  # mesma vigência: corrige a versão em vez de empilhar outra
        i = IntervaloAgenda(turno=dados.turno, estudio_id=dados.estudio_id,
                            vigente_desde=dados.a_partir_de, vigente_ate=ate)
        db.add(i)
    i.horario_inicio, i.horario_fim = h_ini, h_fim
    i.motivo = (dados.motivo or "").strip() or None
    i.criado_por, i.criado_por_nome, i.criado_em = user.id, getattr(user, "full_name", None) or user.email, datetime.utcnow()
    db.commit()
    return {**svc.quadro_intervalos(db, dados.a_partir_de), "historico": svc.historico_intervalos(db)}


@router.delete("/intervalos/{intervalo_id}", status_code=204)
def excluir_intervalo(intervalo_id: int, db: Session = Depends(get_db), _: User = Depends(pode_agenda)):
    i = db.query(IntervaloAgenda).filter(IntervaloAgenda.id == intervalo_id).first()
    if not i:
        raise HTTPException(404, "Mudança de intervalo não encontrada.")
    if i.criado_por is None and i.criado_por_nome == "Sistema":
        raise HTTPException(422, "Esse é o valor fixo do sistema. Para mudar, grave um novo intervalo.")
    if i.vigente_desde < date.today():
        raise HTTPException(422, "Essa mudança já valeu em dias que passaram e fica no histórico. "
                                 "Para mudar daqui para frente, grave um novo intervalo.")
    db.delete(i)
    db.commit()


# ─── Escala de diretores ──────────────────────────────────────────────

@router.get("/escala-dia")
def listar_escala_dia(data: date, db: Session = Depends(get_db), user: User = Depends(pode_ver)):
    """Escala de diretores de um dia (estúdio × turno). Link e chave só para quem edita."""
    editor = user.role in PAPEIS_AGENDA
    return [{
        "turno": e.turno,
        "estudio_id": e.estudio_id,
        "diretor_imagem_id": str(e.diretor_imagem_id) if e.diretor_imagem_id else None,
        "diretor2_imagem_id": str(e.diretor2_imagem_id) if e.diretor2_imagem_id else None,
        "troca_horario": svc.hm(e.troca_horario),
        "trocas": e.trocas(),
        "observacao": e.observacao,
        **({"youtube_link": e.youtube_link, "chave_transmissao": e.chave_transmissao} if editor else {}),
    } for e in db.query(EscalaDiaEstudio).filter(EscalaDiaEstudio.data == data).all()]


@router.post("/escala-dia/copiar")
def copiar_escala_dia(dados: CopiarEscalaDiaIn, db: Session = Depends(get_db), user: User = Depends(pode_agenda)):
    """Copia a escala de um dia para outros dias (substitui a escala desses dias). Feriados ficam de fora."""
    origem = db.query(EscalaDiaEstudio).filter(
        EscalaDiaEstudio.data == dados.de_data, EscalaDiaEstudio.diretor_imagem_id.isnot(None)
    ).all()
    if not origem:
        raise HTTPException(422, "O dia de origem não tem nenhum diretor escalado.")
    copiados, feriados = [], []
    for d in sorted(set(dados.para_datas)):
        if d == dados.de_data:
            continue
        if svc.feriado_do_dia(db, d):
            feriados.append(d.isoformat())
            continue
        # Substitui só os diretores; link e chave do destino ficam (mudam todo dia)
        destino = {(x.turno, x.estudio_id): x for x in db.query(EscalaDiaEstudio).filter(EscalaDiaEstudio.data == d).all()}
        for x in destino.values():
            x.diretor_imagem_id = None
            x.diretor2_imagem_id = None
            x.troca_horario = None
            x.trocas_json = None
            x.observacao = None
        for e in origem:
            x = destino.get((e.turno, e.estudio_id))
            if x is None:
                x = EscalaDiaEstudio(data=d, turno=e.turno, estudio_id=e.estudio_id)
                db.add(x)
            x.diretor_imagem_id = e.diretor_imagem_id
            x.diretor2_imagem_id = e.diretor2_imagem_id
            x.troca_horario = e.troca_horario
            x.trocas_json = e.trocas_json
            x.observacao = e.observacao
            x.atualizado_por = user.id
        for x in destino.values():
            if not x.diretor_imagem_id and not x.youtube_link and not x.chave_transmissao:
                db.delete(x)
        copiados.append(d.isoformat())
    db.commit()
    return {"dias": copiados, "feriados_ignorados": feriados}


def _validar_trocas(db: Session, dados: EscalaDiaIn) -> list:
    """
    Diretores que assumem o estúdio depois do primeiro, em ordem: [(diretor_id, hora), ...].
    Aceita a lista `trocas` ou, de telas antigas, o par diretor2_imagem_id/troca_horario.
    """
    if dados.trocas is not None:
        brutas = [(t.diretor_imagem_id, t.a_partir) for t in dados.trocas]
    elif dados.diretor2_imagem_id:
        brutas = [(dados.diretor2_imagem_id, dados.troca_horario)]
    else:
        brutas = []
    if not brutas:
        return []
    if not dados.diretor_imagem_id:
        raise HTTPException(422, "Escolha o primeiro diretor antes dos que assumem depois.")
    if len(brutas) > MAX_TROCAS:
        raise HTTPException(422, f"No máximo {MAX_TROCAS} trocas de diretor no mesmo turno.")
    resultado, anterior, hora_anterior = [], dados.diretor_imagem_id, None
    for n, (diretor_id, texto) in enumerate(brutas, start=2):
        _diretor_ativo(db, diretor_id)
        if diretor_id == anterior:
            raise HTTPException(422, f"O {n}º diretor precisa ser outra pessoa que o anterior.")
        hora = None
        if texto:
            try:
                hora = svc.parse_hora(texto)
            except ValueError as err:
                raise HTTPException(422, str(err))
        elif len(brutas) > 1:
            raise HTTPException(422, f"Informe a partir de que horas o {n}º diretor assume.")
        if hora and hora_anterior and hora <= hora_anterior:
            raise HTTPException(422, f"O horário do {n}º diretor precisa ser depois do anterior.")
        resultado.append((diretor_id, hora))
        anterior, hora_anterior = diretor_id, hora or hora_anterior
    return resultado


@router.put("/escala-dia")
def definir_escala_dia(
    dados: EscalaDiaIn,
    db: Session = Depends(get_db),
    user: User = Depends(pode_agenda),
):
    turno = _turno_valido(dados.turno)
    _sem_feriado(db, dados.data)
    _estudio_ativo(db, dados.estudio_id)
    _diretor_ativo(db, dados.diretor_imagem_id)
    trocas = _validar_trocas(db, dados)
    e = db.query(EscalaDiaEstudio).filter(
        EscalaDiaEstudio.data == dados.data,
        EscalaDiaEstudio.turno == turno,
        EscalaDiaEstudio.estudio_id == dados.estudio_id,
    ).first()
    if not e:
        e = EscalaDiaEstudio(data=dados.data, turno=turno, estudio_id=dados.estudio_id)
        db.add(e)
    e.diretor_imagem_id = dados.diretor_imagem_id
    # diretor2/troca_horario continuam com o primeiro que assume (telas e relatórios antigos)
    e.diretor2_imagem_id = trocas[0][0] if trocas else None
    e.troca_horario = trocas[0][1] if trocas else None
    e.trocas_json = json.dumps([
        {"diretor_imagem_id": str(d), "a_partir": svc.hm(h)} for d, h in trocas
    ]) if trocas else None
    e.observacao = ((dados.observacao or "").strip() or None) if dados.diretor_imagem_id else None
    if dados.youtube_link is not None:
        e.youtube_link = dados.youtube_link.strip() or None
    if dados.chave_transmissao is not None:
        e.chave_transmissao = dados.chave_transmissao.strip() or None
    if not e.diretor_imagem_id and not e.youtube_link and not e.chave_transmissao:
        # sem diretor e sem transmissão: tira o estúdio/turno da escala do dia
        if e.id:
            db.delete(e)
        else:
            db.expunge(e)
        db.commit()
        return {"ok": True}
    e.atualizado_por = user.id
    e.atualizado_em = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.delete("/escala-dia")
def remover_da_escala(
    data: date,
    turno: str,
    estudio_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(pode_agenda),
):
    """Tira o diretor do estúdio/turno no dia (o link e a chave da transmissão continuam)."""
    e = db.query(EscalaDiaEstudio).filter(
        EscalaDiaEstudio.data == data,
        EscalaDiaEstudio.turno == _turno_valido(turno),
        EscalaDiaEstudio.estudio_id == estudio_id,
    ).first()
    if e:
        if e.youtube_link or e.chave_transmissao:
            e.diretor_imagem_id = e.diretor2_imagem_id = e.troca_horario = e.observacao = None
            e.trocas_json = None
        else:
            db.delete(e)
        db.commit()
    return {"ok": True}


# ─── Transmissão do dia: link do YouTube e chave por estúdio e turno ──

@router.get("/transmissao-dia")
def listar_transmissao_dia(data: date, db: Session = Depends(get_db), _: User = Depends(pode_agenda)):
    """Link e chave de cada estúdio em cada turno do dia (só quem edita a Agenda)."""
    tx = svc.transmissao_do_dia(db, data)
    return [{"turno": t, "estudio_id": est, **v} for (t, est), v in tx.items()]


@router.put("/transmissao-dia")
def definir_transmissao_dia(dados: TransmissaoDiaIn, db: Session = Depends(get_db), user: User = Depends(pode_agenda)):
    """
    Grava o link do YouTube e a chave de vários estúdios/turnos do dia de uma vez.
    Vale para todas as aulas do estúdio no turno, com ou sem diretor escalado.
    Campo vazio apaga o que havia.
    """
    _sem_feriado(db, dados.data)
    linhas = {(x.turno, x.estudio_id): x for x in db.query(EscalaDiaEstudio).filter(EscalaDiaEstudio.data == dados.data).all()}
    gravados = 0
    for it in dados.itens:
        turno = _turno_valido(it.turno)
        link = (it.youtube_link or "").strip() or None
        chave = (it.chave_transmissao or "").strip() or None
        e = linhas.get((turno, it.estudio_id))
        if e is None:
            if not link and not chave:
                continue
            _estudio_ativo(db, it.estudio_id)
            e = EscalaDiaEstudio(data=dados.data, turno=turno, estudio_id=it.estudio_id)
            db.add(e)
            linhas[(turno, it.estudio_id)] = e
        e.youtube_link = link
        e.chave_transmissao = chave
        e.atualizado_por = user.id
        e.atualizado_em = datetime.utcnow()
        if not e.diretor_imagem_id and not link and not chave and e.id:
            db.delete(e)
        gravados += 1
    db.commit()
    return {"ok": True, "gravados": gravados}


# ─── Exportação no formato da planilha ────────────────────────────────

@router.get("/exportar")
def exportar_excel(
    data_inicio: date,
    data_fim: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(pode_ver),
):
    fim = data_fim or data_inicio
    if data_inicio > fim:
        raise HTTPException(422, "A data de início não pode ser maior que a data de fim.")
    if (fim - data_inicio).days + 1 > MAX_DIAS_EXPORTACAO:
        raise HTTPException(422, f"Exporte no máximo {MAX_DIAS_EXPORTACAO} dias por vez.")
    buf = exportar_periodo(db, data_inicio, fim, user_role=current_user.role)
    nome = (
        f"agenda_estudios_{data_inicio.strftime('%d-%m-%Y')}"
        + (f"_a_{fim.strftime('%d-%m-%Y')}" if fim != data_inicio else "")
        + ".xlsx"
    )
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


# ─── Feriados ─────────────────────────────────────────────────────────

@router.get("/feriados")
def listar_feriados(
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(pode_ver),
):
    q = db.query(FeriadoAgenda)
    if data_inicio:
        q = q.filter(FeriadoAgenda.data >= data_inicio)
    if data_fim:
        q = q.filter(FeriadoAgenda.data <= data_fim)
    return [{"id": f.id, "data": f.data.isoformat(), "nome": f.nome} for f in q.order_by(FeriadoAgenda.data).all()]


@router.post("/feriados", status_code=201)
def marcar_feriado(dados: FeriadoIn, db: Session = Depends(get_db), user: User = Depends(pode_agenda)):
    f = db.query(FeriadoAgenda).filter(FeriadoAgenda.data == dados.data).first()
    if not f:
        f = FeriadoAgenda(data=dados.data, criado_por=user.id)
        db.add(f)
    f.nome = dados.nome.strip()
    db.commit()
    db.refresh(f)
    return {"id": f.id, "data": f.data.isoformat(), "nome": f.nome}


@router.delete("/feriados/{feriado_id}", status_code=204)
def desmarcar_feriado(feriado_id: int, db: Session = Depends(get_db), _: User = Depends(pode_agenda)):
    db.query(FeriadoAgenda).filter(FeriadoAgenda.id == feriado_id).delete(synchronize_session=False)
    db.commit()


# ─── Observações dos blocos (TomTicket e anotações) ───────────────────

@router.post("/observacoes", status_code=201)
def criar_observacao(dados: ObservacaoIn, db: Session = Depends(get_db), user: User = Depends(pode_agenda)):
    if bool(dados.grade_id) == bool(dados.agendamento_id):
        raise HTTPException(422, "Informe a aula (grade_id) ou o agendamento (agendamento_id).")
    if dados.agendamento_id:
        _get_agendamento(db, dados.agendamento_id)
    else:
        _aula_prevista(db, dados.data, dados.grade_id)
    o = ObservacaoAgenda(
        data=dados.data, grade_id=dados.grade_id, agendamento_id=dados.agendamento_id,
        texto=dados.texto.strip(), link=(dados.link or "").strip() or None,
        autor_id=user.id, autor_nome=user.full_name,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return svc.observacao_to_dict(o)


@router.delete("/observacoes/{observacao_id}", status_code=204)
def excluir_observacao(observacao_id: int, db: Session = Depends(get_db), _: User = Depends(pode_agenda)):
    db.query(ObservacaoAgenda).filter(ObservacaoAgenda.id == observacao_id).delete(synchronize_session=False)
    db.commit()


# ─── Estúdios: Libras e prioridade para evento ────────────────────────

@router.get("/estudios-config")
def listar_config_estudios(db: Session = Depends(get_db), _: User = Depends(pode_ver)):
    cfg = svc.config_estudios(db)
    return [{
        "estudio_id": e.id, "nome": e.nome,
        "libras": bool(cfg.get(e.id) and cfg[e.id].libras),
        "prioridade_evento": cfg[e.id].prioridade_evento if cfg.get(e.id) else None,
    } for e in svc.estudios_ativos(db)]


@router.put("/estudios-config/{estudio_id}")
def salvar_config_estudio(estudio_id: int, dados: ConfigEstudioIn, db: Session = Depends(get_db),
                          user: User = Depends(pode_agenda)):
    _estudio_ativo(db, estudio_id)
    c = db.query(ConfigEstudioAgenda).filter(ConfigEstudioAgenda.estudio_id == estudio_id).first()
    if not c:
        c = ConfigEstudioAgenda(estudio_id=estudio_id)
        db.add(c)
    c.libras = dados.libras
    c.prioridade_evento = dados.prioridade_evento
    c.atualizado_por = user.id
    db.commit()
    return {"estudio_id": estudio_id, "libras": c.libras, "prioridade_evento": c.prioridade_evento}


@router.get("/sugestoes")
def sugestoes_de_estudio(
    data: date,
    inicio: str,
    fim: str,
    para: str = Query("aula", pattern="^(aula|evento)$"),
    grade_id: Optional[str] = Query(None, description="Aula que está sendo remanejada (não conta como ocupação)"),
    agendamento_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(pode_ver),
):
    h_ini, h_fim = _horarios(inicio, fim)
    return svc.sugerir_estudios(db, data, h_ini, h_fim, para=para,
                                ignorar_grade_id=grade_id, ignorar_agendamento_id=agendamento_id)


# ─── Estúdio fixo da aula (o diretor-chefe define; a grade guarda) ────

@router.put("/aulas/estudio-fixo")
def definir_estudio_fixo(dados: EstudioFixoIn, db: Session = Depends(get_db), user: User = Depends(pode_agenda)):
    """
    Muda o estúdio da aula na grade (vale para todas as semanas). O horário não
    muda. Bloqueia se outra aula da grade já usa esse estúdio no mesmo horário.
    """
    g = db.query(Grade).filter(Grade.id == dados.grade_id).first()
    if not g:
        raise HTTPException(404, "Aula da grade não encontrada.")
    destino = _estudio_ativo(db, dados.estudio_id)
    if svc.fora_do_funcionamento(destino, g.horario_inicio, g.horario_fim):
        raise HTTPException(422, f"{destino.nome} não funciona nesse horário "
                                 f"({svc.hm(destino.horario_inicio)}–{svc.hm(destino.horario_fim)}).")
    hoje = date.today()
    dia_ref = hoje + timedelta(days=(g.dia_semana - hoje.weekday()) % 7)
    choques = [
        s for s in svc.grade_do_dia(db, dia_ref)
        if s["grade_id"] != str(g.id) and s["estudio_id"] == destino.id
        and svc.sobrepoe(g.horario_inicio, g.horario_fim, s["inicio"], s["fim"])
    ]
    if choques:
        raise HTTPException(409, f"{destino.nome} já tem aula da grade nesse horário: "
                                 + "; ".join(svc.descrever_aula(x) for x in choques))
    g.estudio_id = destino.id
    db.commit()
    return {"ok": True, "grade_id": str(g.id), "estudio_id": destino.id, "estudio": destino.nome}


# ─── Estúdio da aula (relatório do assistente) ────────────────────────

@router.get("/aulas-da-turma")
def listar_aulas_da_turma(
    turma_id: UUID, data: date, db: Session = Depends(get_db), _: User = Depends(pode_ver),
):
    """Aulas da grade da turma na data (o chefe escolhe qual aula a gravação antecipada substitui)."""
    return svc.aulas_da_turma_no_dia(db, turma_id, data)


@router.get("/estudio-da-aula")
def consultar_estudio_da_aula(
    turma_id: UUID,
    data: date,
    horario: Optional[str] = Query(None, description="'2º Horário' ou '07:30 às 08:30'"),
    turno: Optional[str] = Query(None),
    inicio: Optional[str] = Query(None),
    disciplina_id: Optional[UUID] = Query(None),
    agendamento_id: Optional[UUID] = Query(None, description="Aula marcada na Agenda (antecipada, reposição…)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """
    Estúdio onde a aula acontece na data, definido pela grade e pela Agenda (remanejamento do dia),
    com o diretor escalado e o link da transmissão do estúdio no turno. A chave só vai para quem
    edita a Agenda e para o diretor escalado.
    """
    h_ini = None
    if inicio:
        try:
            h_ini = svc.parse_hora(inicio)
        except ValueError as err:
            raise HTTPException(422, str(err))
    r = svc.estudio_da_aula(db, turma_id, data, horario_aula=horario, turno=turno, inicio=h_ini,
                            disciplina_id=disciplina_id, agendamento_id=agendamento_id)
    if "chave_transmissao" in r and not pode_ver_chave(db, user, r.get("diretor_imagem_id")):
        r["chave_transmissao"] = None
    return r


def pode_ver_chave(db: Session, user: User, diretor_escalado_id) -> bool:
    """Chave de transmissão: quem edita a Agenda e o diretor escalado no estúdio/turno."""
    if user.role in PAPEIS_AGENDA:
        return True
    if user.role != "diretor_imagem" or not diretor_escalado_id:
        return False
    proprio = db.query(DiretorImagem).filter(DiretorImagem.user_id == user.id).first()
    return bool(proprio and str(proprio.id) == str(diretor_escalado_id))


# ─── Grade Horária da turma: estúdio do dia e aulas fora da grade ─────

@router.get("/semana-turma")
def semana_da_turma(
    turma_id: UUID,
    data_inicio: date,
    data_fim: date,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Remanejamentos/cancelamentos do dia e aulas marcadas na Agenda fora da grade (antecipada, reposição…)."""
    if data_fim < data_inicio or (data_fim - data_inicio).days > 31:
        raise HTTPException(422, "Período inválido (máximo 31 dias).")
    return svc.semana_da_turma(db, turma_id, data_inicio, data_fim)


# ─── Grade do diretor de imagem: estúdios em que ele está escalado ────

PAPEIS_MINHA_ESCALA = ("admin", "diretor_chefe", "diretor_imagem")


@router.get("/minha-escala")
def minha_escala(
    data: date = Query(default_factory=date.today),
    diretor_id: Optional[UUID] = Query(None, description="Admin/Diretor-Chefe: ver a escala de outro diretor"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*PAPEIS_MINHA_ESCALA)),
):
    """Estúdios e turnos do diretor no dia, com as aulas de cada um e o link/chave da transmissão."""
    if diretor_id and user.role in PAPEIS_AGENDA:
        diretor = db.query(DiretorImagem).filter(DiretorImagem.id == diretor_id).first()
    else:
        diretor = db.query(DiretorImagem).filter(DiretorImagem.user_id == user.id).first()
    if not diretor:
        raise HTTPException(404, "Seu usuário não está ligado a um diretor de imagem. Fale com o diretor-chefe.")
    resp = svc.minha_escala(db, data, diretor.id)
    resp["diretor"] = {"id": str(diretor.id), "nome": diretor.nome}
    return resp
