"""
Agenda de Estúdios — monta o dia (o que era uma aba da planilha) a partir de:

* grade horária vigente das turmas ativas (aulas fixas por estúdio);
* escala de diretores de imagem (fixa por dia da semana + trocas do dia);
* agendamentos extras, cancelamentos e remanejamentos lançados na agenda;
* horários trancados (bloqueios recorrentes por estúdio).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.agenda_estudio import (
    AgendamentoEstudio, BloqueioEstudio, ConfigEstudioAgenda, EscalaDiaEstudio,
    FeriadoAgenda, IntervaloAgenda, ObservacaoAgenda,
)
from app.models.auxiliares import Grade, Professor
from app.models.diretor_imagem import DiretorImagem
from app.models.infraestrutura import CanalIptvModel, Estudio, GradeVersao
from app.models.turma import Turma
from app.services.horario_resolver import get_tipo_horario, horarios_padrao

DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]

TURNOS = [
    # chave, rótulo, início e fim padrão da coluna de horários da planilha
    ("manha", "Manhã", time(7, 0), time(12, 20)),
    ("tarde", "Tarde", time(12, 50), time(18, 20)),
    ("noite", "Noite", time(18, 0), time(22, 30)),
]
TURNO_LABEL = {k: rotulo for k, rotulo, _, _ in TURNOS}

# Regras da planilha para um horário livre ficar "verde" (disponível):
DURACAO_MINIMA_MIN = 45   # a menor aula tem 45 min — espaço menor não serve para agendar
MARGEM_SEGURANCA_MIN = 10  # folga antes da próxima aula do estúdio (ex.: tarde do Est. 3 vai até 18:20)
SEMANAS_SEM_REGISTRO = 4   # aula prevista sem relatório nas últimas N semanas → avisar


AULA_CANCELADA = "AULA_CANCELADA"
AULA_REMANEJADA = "AULA_REMANEJADA"
OCORRENCIAS_DE_AULA = (AULA_CANCELADA, AULA_REMANEJADA)

# Tipos de agendamento e cores combinadas com os diretores (reunião de 08/10):
# verde = aula/gravação de aula; azul = evento (SEDUC ou outro departamento);
# amarelo = assíncrona; vermelho fica só para cancelado e trancado.
TIPOS_AGENDAMENTO = {
    # Reunião 26/10/2026: as gravações viraram um tipo só; antecipada = Gravação + SEDUC
    # ligada à aula da grade; reposição = Gravação marcada como reposição.
    "GRAVACAO": {"label": "Gravação", "cor": "#0d9488"},
    "AULA_EXTRA": {"label": "Aula extra (fora da grade)", "cor": "#22c55e"},
    "EVENTO": {"label": "Evento (SEDUC / departamento)", "cor": "#2563eb"},
    # Tipos antigos: continuam válidos nos registros antigos (convertidos para Gravação ao subir)
    "GRAVACAO_ANTECIPADA": {"label": "Gravação antecipada (antigo)", "cor": "#16a34a", "oculto": True},
    "REPOSICAO": {"label": "Reposição (antigo)", "cor": "#059669", "oculto": True},
    "ASSINCRONA": {"label": "Assíncrona / NP (antigo)", "cor": "#eab308", "oculto": True},
    "CURSO_TECNICO": {"label": "Gravação curso técnico (antigo)", "cor": "#0d9488", "oculto": True},
    "REGRAVACAO": {"label": "Regravação (antigo)", "cor": "#65a30d", "oculto": True},
    "PODCAST": {"label": "Podcast", "cor": "#7c3aed"},
    "MANUTENCAO": {"label": "Manutenção", "cor": "#78716c"},
    "OUTRO": {"label": "Outro", "cor": "#6366f1"},
    # Antigo "Reserva (UAPI / externo)": hoje é Evento com nome livre. Continua
    # aparecendo nos registros antigos, mas não é oferecido para novos.
    "RESERVA": {"label": "Reserva (antigo — use Evento)", "cor": "#3b82f6", "oculto": True},
}
TIPOS_DE_EVENTO = ("EVENTO", "PODCAST", "RESERVA")      # podem mudar de horário (vertical)
TIPOS_GRAVACAO = ("GRAVACAO", "GRAVACAO_ANTECIPADA", "REPOSICAO", "ASSINCRONA", "CURSO_TECNICO", "REGRAVACAO")
TIPOS_DE_AULA = TIPOS_GRAVACAO + ("AULA_EXTRA",)
COR_CANCELADO = "#dc2626"
ROTULO_ESPECIAL = {
    AULA_CANCELADA: ("Aula cancelada", COR_CANCELADO),
    AULA_REMANEJADA: ("Aula remanejada", "#64748b"),
}
BLOQUEIO_TRANCADO = "TRANCADO"
BLOQUEIO_SOB_DEMANDA = "SOB_DEMANDA"
MINIMO_AULAS_SOB_DEMANDA = 3
TEXTOS_PRONTOS = [
    "Aula cancelada pelo professor.",
    "Aula cancelada por evento no estúdio.",
    "Professor atrasou.",
    "Problema de áudio.",
    "Problema de vídeo / transmissão.",
    "Queda de internet.",
    "Aula remanejada por manutenção no estúdio.",
    "Gravação refeita.",
]
DEPARTAMENTOS_SUGERIDOS = ["UETEV", "SUGED", "Pedagógico", "Coordenação", "NTI", "Comunicação"]

STATUS_AGENDADO = "AGENDADO"
STATUS_CANCELADO = "CANCELADO"


# ─── Helpers de horário ───────────────────────────────────────────────

def hm(t: Optional[time]) -> Optional[str]:
    return t.strftime("%H:%M") if t else None


def minutos(t: time) -> int:
    return t.hour * 60 + t.minute


def hora_de_min(m: int) -> str:
    m = max(0, min(m, 23 * 60 + 59))
    return f"{m // 60:02d}:{m % 60:02d}"


def parse_hora(valor: str) -> time:
    try:
        h, m = str(valor).strip().split(":")[:2]
        return time(int(h), int(m))
    except Exception:
        raise ValueError(f"Horário inválido: '{valor}'. Use HH:MM.")




def turno_do_horario(inicio: time) -> str:
    """Turno pelo horário de início (mesma regra do restante do sistema)."""
    m = minutos(inicio)
    if m < 12 * 60 + 30:
        return "manha"
    if m < 18 * 60:
        return "tarde"
    return "noite"


def sobrepoe(ini_a: time, fim_a: time, ini_b: time, fim_b: time) -> bool:
    return ini_a < fim_b and ini_b < fim_a


def _is_gravacao_sem_horario(g: Grade) -> bool:
    return bool(g.horario_inicio) and g.horario_inicio.strftime("%H:%M") == "00:00"


def _ordinal_do_slot(turma: Turma, inicio: time) -> Optional[str]:
    """'2º Horário' quando o início bate com a tabela padrão da modalidade da turma."""
    try:
        tipo = get_tipo_horario(turma.turno, turma.nomenclatura_padrao or turma.nome, turma.modalidade)
        alvo = hm(inicio)
        for ordinal, ini, _fim in horarios_padrao(tipo):
            if ini == alvo:
                return ordinal
    except Exception:
        return None
    return None


def turma_label(turma: Optional[Turma]) -> Optional[str]:
    if not turma:
        return None
    return turma.nomenclatura_padrao or turma.nome


# ─── Grade do dia ─────────────────────────────────────────────────────

def _slots_vigentes(db: Session, data: date) -> List[Tuple[Grade, Turma]]:
    """
    Slots da grade previstos na data — MESMA regra dos "Previstos" da Auditoria
    (audit-stats), para os números baterem:

    * só turmas ativas;
    * slot legado (sem versão) ou de versão de grade ATIVA;
    * turma que tem versão ativa (Grade v2) ignora os slots legados — senão a
      mesma aula aparece duas vezes;
    * vigência (início/fim) vale para os slots legados.
    """
    turmas_com_versao = {
        tid for (tid,) in db.query(Grade.turma_id)
        .join(GradeVersao, Grade.grade_versao_id == GradeVersao.id)
        .filter(GradeVersao.is_active == True)  # noqa: E712
        .distinct()
        .all()
    }
    q = (
        db.query(Grade, Turma)
        .join(Turma, Grade.turma_id == Turma.id)
        .outerjoin(GradeVersao, Grade.grade_versao_id == GradeVersao.id)
        .filter(
            Turma.is_active == True,  # noqa: E712
            Grade.dia_semana == data.weekday(),
            or_(Grade.grade_versao_id.is_(None), GradeVersao.is_active == True),  # noqa: E712
        )
        .order_by(Grade.horario_inicio)
    )
    saida = []
    for g, turma in q.all():
        if g.grade_versao_id is None:
            if turma.id in turmas_com_versao:
                continue
            if g.vigencia_inicio and g.vigencia_inicio > data:
                continue
            if g.vigencia_fim and g.vigencia_fim < data:
                continue
        saida.append((g, turma))
    return saida


def grade_do_dia_detalhado(db: Session, data: date) -> Tuple[List[dict], List[dict]]:
    """(slots do dia sem duplicatas, duplicatas encontradas na grade)."""
    canais = {c.id: c.nome for c in db.query(CanalIptvModel).all()}
    slots, duplicados, vistos = [], [], {}
    for g, turma in _slots_vigentes(db, data):
        canal = canais.get(g.canal_iptv_id) if g.canal_iptv_id else (
            f"Canal {g.canal_iptv}" if g.canal_iptv else None
        )
        gravacao = _is_gravacao_sem_horario(g)
        s = {
            "grade_id": str(g.id),
            "turma_id": str(turma.id),
            "turma": turma_label(turma),
            "turma_modalidade": turma.modalidade,
            "canal": canal,
            "estudio_id": g.estudio_id,
            "disciplina_id": str(g.disciplina_id) if g.disciplina_id else None,
            "disciplina": g.disciplina.nome if g.disciplina else None,
            "professor": g.professor.nome if g.professor_id and g.professor else None,
            "professor_id": str(g.professor_id) if g.professor_id else None,
            "inicio": g.horario_inicio,
            "fim": g.horario_fim,
            "tipo_slot": g.tipo_slot or "aula",
            "gravacao_sem_horario": gravacao,
            "ordinal": None if gravacao else _ordinal_do_slot(turma, g.horario_inicio),
        }
        chave = (s["turma_id"], s["estudio_id"], s["inicio"], s["fim"], s["disciplina_id"])
        if chave in vistos:
            duplicados.append(s)
            continue
        vistos[chave] = s
        slots.append(s)
    return slots, duplicados


def grade_do_dia(db: Session, data: date) -> List[dict]:
    return grade_do_dia_detalhado(db, data)[0]


def estudios_ativos(db: Session) -> List[Estudio]:
    """Estúdios ativos na ordem numérica (Estúdio 2 antes de Estúdio 10)."""
    def ordem(e: Estudio):
        m = re.search(r"(\d+)", e.nome or "")
        return (0 if m else 1, int(m.group(1)) if m else 0, e.nome or "")
    return sorted(db.query(Estudio).filter(Estudio.ativo == True).all(), key=ordem)  # noqa: E712


def fora_do_funcionamento(est: Optional[Estudio], inicio: time, fim: time) -> bool:
    if not est or est.funciona_24h or not est.horario_inicio or not est.horario_fim:
        return False
    return inicio < est.horario_inicio or fim > est.horario_fim


# ─── Escala de diretores ──────────────────────────────────────────────

def escala_do_dia(db: Session, data: date) -> Dict[Tuple[str, int], dict]:
    """
    (turno, estudio_id) → diretor escalado NAQUELE DIA. A escala é diária: o
    diretor-chefe monta a de cada dia (pode copiar de outro dia). Estúdio sem
    linha na escala do dia = sem diretor.
    """
    resultado: Dict[Tuple[str, int], dict] = {}
    linhas = db.query(EscalaDiaEstudio).filter(EscalaDiaEstudio.data == data).all()
    nomes = _nomes_diretores(db, {t["diretor_imagem_id"] for e in linhas for t in e.trocas()})
    for e in linhas:
        if not e.diretor_imagem_id:
            continue
        trocas = [{"diretor_id": t["diretor_imagem_id"], "nome": nomes.get(t["diretor_imagem_id"]),
                   "a_partir": t.get("a_partir")} for t in e.trocas()]
        resultado[(e.turno, e.estudio_id)] = {
            "trocas": trocas,
            "diretor_id": str(e.diretor_imagem_id),
            "nome": e.diretor.nome if e.diretor else None,
            "ativo": bool(e.diretor and e.diretor.is_active),
            "origem": "dia",
            "observacao": e.observacao,
            "diretor2_id": str(e.diretor2_imagem_id) if e.diretor2_imagem_id else None,
            "nome2": e.diretor2.nome if e.diretor2 else None,
            "troca_horario": hm(e.troca_horario),
            "youtube_link": e.youtube_link,
            "chave_transmissao": e.chave_transmissao,
        }
    return resultado


def _nomes_diretores(db: Session, ids) -> Dict[str, str]:
    import uuid as _uuid
    validos = []
    for i in ids:
        try:
            validos.append(_uuid.UUID(str(i)))
        except (ValueError, TypeError):
            pass
    ids = validos
    if not ids:
        return {}
    return {str(d.id): d.nome for d in db.query(DiretorImagem).filter(DiretorImagem.id.in_(ids)).all()}


def diretores_do_turno(d: Optional[dict]) -> List[Tuple[str, str]]:
    """(id, nome) de todos os diretores do estúdio no turno: o escalado e os que assumiram depois."""
    if not d or not d.get("diretor_id"):
        return []
    lista = [(d["diretor_id"], d.get("nome"))]
    lista += [(t["diretor_id"], t.get("nome")) for t in d.get("trocas", [])]
    return lista


def transmissao_do_dia(db: Session, data: date) -> Dict[Tuple[str, int], dict]:
    """
    (turno, estudio_id) → link do YouTube e chave de transmissão do dia. O diretor-chefe
    informa uma vez por estúdio e turno; vale para todas as aulas desse estúdio/turno no dia,
    com ou sem diretor escalado.
    """
    return {
        (e.turno, e.estudio_id): {"youtube_link": e.youtube_link, "chave_transmissao": e.chave_transmissao}
        for e in db.query(EscalaDiaEstudio).filter(EscalaDiaEstudio.data == data).all()
        if e.youtube_link or e.chave_transmissao
    }


def transmissao_do_estudio(db: Session, data: date, turno: Optional[str], estudio_nome: Optional[str]) -> dict:
    """
    Link e chave informados pelo diretor-chefe para o estúdio (pelo nome, como gravado no
    relatório: "Estúdio 04" ou "ESTÚDIO 4") e turno ("Manhã", "manha"…) no dia.
    """
    from app.services.idr_txt_parser import norm_estudio
    vazio = {"youtube_link": None, "chave_transmissao": None}
    if not data or not turno or not estudio_nome:
        return vazio
    t = (turno or "").strip().lower()
    t = "manha" if "manh" in t else "tarde" if "tard" in t else "noite" if "noit" in t else t
    alvo = norm_estudio(estudio_nome)
    est = next((e for e in db.query(Estudio).all() if norm_estudio(e.nome) == alvo), None)
    if not est:
        return vazio
    return transmissao_do_dia(db, data).get((t, est.id)) or vazio


def transmissao_da_aula(db: Session, data: date, inicio: Optional[time], estudio_id: Optional[int]) -> dict:
    """Link e chave do estúdio no turno da aula (vazio se o diretor-chefe ainda não informou)."""
    if not estudio_id or inicio is None:
        return {"youtube_link": None, "chave_transmissao": None}
    return transmissao_do_dia(db, data).get((turno_do_horario(inicio), estudio_id)) or {
        "youtube_link": None, "chave_transmissao": None}


# ─── Feriados ─────────────────────────────────────────────────────────

def feriado_do_dia(db: Session, data: date) -> Optional[FeriadoAgenda]:
    return db.query(FeriadoAgenda).filter(FeriadoAgenda.data == data).first()


# ─── Configuração dos estúdios (Libras, prioridade para evento) ───────

def config_estudios(db: Session) -> Dict[int, ConfigEstudioAgenda]:
    return {c.estudio_id: c for c in db.query(ConfigEstudioAgenda).all()}


# ─── Observações ──────────────────────────────────────────────────────

def observacao_to_dict(o: ObservacaoAgenda) -> dict:
    return {
        "id": o.id,
        "data": o.data.isoformat(),
        "grade_id": str(o.grade_id) if o.grade_id else None,
        "agendamento_id": str(o.agendamento_id) if o.agendamento_id else None,
        "texto": o.texto,
        "link": o.link,
        "autor": o.autor_nome,
        "criado_em": o.criado_em.isoformat() if o.criado_em else None,
    }


def observacoes_do_dia(db: Session, data: date) -> Dict[str, List[dict]]:
    """chave ('g:<grade_id>' ou 'a:<agendamento_id>') → observações em ordem."""
    saida: Dict[str, List[dict]] = {}
    for o in (db.query(ObservacaoAgenda).filter(ObservacaoAgenda.data == data)
              .order_by(ObservacaoAgenda.criado_em, ObservacaoAgenda.id).all()):
        chave = f"g:{o.grade_id}" if o.grade_id else (f"a:{o.agendamento_id}" if o.agendamento_id else None)
        if chave:
            saida.setdefault(chave, []).append(observacao_to_dict(o))
    return saida


# ─── Ocorrências das aulas no dia (cancelada / remanejada) ────────────

def ocorrencias_do_dia(db: Session, data: date) -> Dict[str, AgendamentoEstudio]:
    """grade_id → cancelamento ou remanejamento lançado para a aula nesta data."""
    rows = db.query(AgendamentoEstudio).filter(
        AgendamentoEstudio.data == data,
        AgendamentoEstudio.tipo.in_(OCORRENCIAS_DE_AULA),
    ).all()
    return {str(r.grade_id): r for r in rows if r.grade_id}


def grade_ids_cancelados(db: Session, data: date) -> Dict[str, AgendamentoEstudio]:
    return {g: o for g, o in ocorrencias_do_dia(db, data).items() if o.tipo == AULA_CANCELADA}


def aulas_do_dia(db: Session, data: date) -> List[dict]:
    """
    Aulas da grade no dia já com o que foi lançado na agenda:
    `estudio_efetivo` é onde a aula acontece (o destino, se foi remanejada);
    `ocupa` diz se ela ocupa estúdio (não cancelada, com horário e estúdio).
    """
    ocorr = ocorrencias_do_dia(db, data)
    saida = []
    for s in grade_do_dia(db, data):
        o = ocorr.get(s["grade_id"])
        s = dict(s)
        s["ocorrencia"] = o
        s["cancelada"] = bool(o and o.tipo == AULA_CANCELADA)
        s["remanejada"] = bool(o and o.tipo == AULA_REMANEJADA)
        s["estudio_efetivo"] = o.estudio_id if s["remanejada"] else s["estudio_id"]
        # Gravação da grade (MP) remanejada com outro horário neste dia: vale o horário do dia
        s["inicio_grade"], s["fim_grade"] = s["inicio"], s["fim"]
        s["horario_mudou"] = False
        if s["remanejada"] and o.horario_inicio and o.horario_fim and (
            o.horario_inicio != s["inicio"] or o.horario_fim != s["fim"]
        ):
            s["inicio"], s["fim"] = o.horario_inicio, o.horario_fim
            s["horario_mudou"] = True
        s["ocupa"] = bool(s["estudio_efetivo"]) and not s["cancelada"] and not s["gravacao_sem_horario"]
        saida.append(s)
    return saida


# ─── Horários trancados ───────────────────────────────────────────────

def bloqueios_do_dia(db: Session, data: date) -> Dict[int, List[BloqueioEstudio]]:
    saida: Dict[int, List[BloqueioEstudio]] = {}
    for b in db.query(BloqueioEstudio).filter(BloqueioEstudio.ativo == True).all():  # noqa: E712
        if data.weekday() in b.dias():
            saida.setdefault(b.estudio_id, []).append(b)
    return saida


def bloqueio_to_dict(b: BloqueioEstudio) -> dict:
    return {
        "id": b.id,
        "estudio_id": b.estudio_id,
        "estudio_nome": b.estudio.nome if b.estudio else None,
        "dias_semana": sorted(b.dias()),
        "horario_inicio": hm(b.horario_inicio),
        "horario_fim": hm(b.horario_fim),
        "motivo": b.motivo,
        "ativo": b.ativo,
        "tipo": b.tipo or BLOQUEIO_TRANCADO,
        "minimo_aulas": b.minimo_aulas,
    }


def eh_sob_demanda(b: BloqueioEstudio) -> bool:
    return (b.tipo or BLOQUEIO_TRANCADO) == BLOQUEIO_SOB_DEMANDA


# ─── Intervalos do turno ──────────────────────────────────────────────

TURNOS_COM_INTERVALO = ("manha", "tarde")


def _vale_no_dia(i: IntervaloAgenda, data: date) -> bool:
    return i.vigente_desde <= data and (i.vigente_ate is None or i.vigente_ate >= data)


def _versao_do_dia(lista: List[IntervaloAgenda], data: date) -> Optional[IntervaloAgenda]:
    """A versão que vale no dia: a de "só neste dia" vence; depois a mais recente."""
    validas = [i for i in lista if _vale_no_dia(i, data)]
    if not validas:
        return None
    return max(validas, key=lambda i: (i.vigente_ate is not None, i.vigente_desde,
                                       i.criado_em or datetime.min, i.id or 0))


def intervalo_to_dict(i: Optional[IntervaloAgenda], origem: str) -> Optional[dict]:
    if not i or not i.horario_inicio or not i.horario_fim:
        return None
    return {"id": i.id, "inicio": hm(i.horario_inicio), "fim": hm(i.horario_fim), "origem": origem,
            "vigente_desde": i.vigente_desde.isoformat(),
            "so_neste_dia": i.vigente_ate is not None, "motivo": i.motivo}


def intervalos_do_dia(db: Session, data: date, estudio_ids) -> Dict[Tuple[str, int], dict]:
    """(turno, estudio_id) → intervalo que vale no dia (exceção do estúdio ou o padrão)."""
    grupos: Dict[Tuple[str, Optional[int]], List[IntervaloAgenda]] = {}
    for i in db.query(IntervaloAgenda).filter(IntervaloAgenda.vigente_desde <= data).all():
        grupos.setdefault((i.turno, i.estudio_id), []).append(i)
    saida: Dict[Tuple[str, int], dict] = {}
    for turno in TURNOS_COM_INTERVALO:
        padrao = _versao_do_dia(grupos.get((turno, None), []), data)
        for est_id in estudio_ids:
            propria = _versao_do_dia(grupos.get((turno, est_id), []), data)
            if propria and propria.horario_inicio:
                v = intervalo_to_dict(propria, "estudio")
            else:
                v = intervalo_to_dict(padrao, "padrao")
            if v:
                saida[(turno, est_id)] = v
    return saida


def intervalo_do_estudio(db: Session, data: date, estudio_id: int, inicio: time) -> Optional[dict]:
    return intervalos_do_dia(db, data, [estudio_id]).get((turno_do_horario(inicio), estudio_id))


def historico_intervalos(db: Session) -> List[dict]:
    nomes = {e.id: e.nome for e in db.query(Estudio).all()}
    saida = []
    for i in db.query(IntervaloAgenda).order_by(IntervaloAgenda.vigente_desde.desc(), IntervaloAgenda.id.desc()).all():
        saida.append({
            "id": i.id, "turno": i.turno, "turno_label": TURNO_LABEL.get(i.turno, i.turno),
            "estudio_id": i.estudio_id, "estudio_nome": nomes.get(i.estudio_id) if i.estudio_id else None,
            "inicio": hm(i.horario_inicio), "fim": hm(i.horario_fim),
            "vigente_desde": i.vigente_desde.isoformat(),
            "vigente_ate": i.vigente_ate.isoformat() if i.vigente_ate else None,
            "motivo": i.motivo, "criado_por": i.criado_por_nome,
            "criado_em": i.criado_em.isoformat() if i.criado_em else None,
        })
    return saida


def quadro_intervalos(db: Session, data: date) -> dict:
    """O que vale no dia, por turno: o padrão e o de cada estúdio ativo."""
    estudios = estudios_ativos(db)
    vale = intervalos_do_dia(db, data, [e.id for e in estudios])
    turnos = []
    for turno in TURNOS_COM_INTERVALO:
        padrao = _versao_do_dia([i for i in db.query(IntervaloAgenda).filter(
            IntervaloAgenda.turno == turno, IntervaloAgenda.estudio_id.is_(None),
            IntervaloAgenda.vigente_desde <= data).all()], data)
        turnos.append({
            "turno": turno, "label": TURNO_LABEL[turno],
            "padrao": intervalo_to_dict(padrao, "padrao"),
            "estudios": [{"estudio_id": e.id, "estudio_nome": e.nome, "intervalo": vale.get((turno, e.id))}
                         for e in estudios],
        })
    return {"data": data.isoformat(), "turnos": turnos}


# ─── Agendamentos ─────────────────────────────────────────────────────

def agendamento_to_dict(a: AgendamentoEstudio) -> dict:
    info = TIPOS_AGENDAMENTO.get(a.tipo, {})
    rotulo, cor = ROTULO_ESPECIAL.get(a.tipo, (info.get("label", a.tipo), info.get("cor", "#6366f1")))
    return {
        "id": str(a.id),
        "data": a.data.isoformat(),
        "estudio_id": a.estudio_id,
        "estudio_nome": a.estudio.nome if a.estudio else None,
        "horario_inicio": hm(a.horario_inicio),
        "horario_fim": hm(a.horario_fim),
        "turno": turno_do_horario(a.horario_inicio),
        "tipo": a.tipo,
        "tipo_label": rotulo,
        "cor": cor,
        "titulo": a.titulo,
        "descricao": a.descricao,
        "professor": a.professor,
        "turma_id": str(a.turma_id) if a.turma_id else None,
        "turma": turma_label(a.turma),
        "grade_id": str(a.grade_id) if a.grade_id else None,
        "canal_iptv_id": a.canal_iptv_id,
        "canal": a.canal.nome if a.canal else None,
        "departamento": a.departamento,
        "chave_transmissao": a.chave_transmissao,
        "nome_evento": a.nome_evento,
        "responsavel_evento": a.responsavel_evento,
        "solicitante_antecipacao": a.solicitante_antecipacao,
        "data_referencia": a.data_referencia.isoformat() if a.data_referencia else None,
        "motivo_referencia": a.motivo_referencia,
        "grade_exibicao_id": str(a.grade_exibicao_id) if getattr(a, "grade_exibicao_id", None) else None,
        "reposicao": bool(getattr(a, "reposicao", False)),
        "gravacao": a.tipo in TIPOS_GRAVACAO,
        "chamado": a.chamado,
        "chamado_link": a.chamado_link,
        "status": a.status,
    }


def agendamentos_ativos_do_estudio(
    db: Session, data: date, estudio_id: int, ignorar_id: Optional[UUID] = None,
) -> List[AgendamentoEstudio]:
    q = db.query(AgendamentoEstudio).filter(
        AgendamentoEstudio.data == data,
        AgendamentoEstudio.estudio_id == estudio_id,
        AgendamentoEstudio.status == STATUS_AGENDADO,
        ~AgendamentoEstudio.tipo.in_(OCORRENCIAS_DE_AULA),
    )
    if ignorar_id:
        q = q.filter(AgendamentoEstudio.id != ignorar_id)
    return q.all()


def conflitos(
    db: Session, data: date, estudio_id: int, inicio: time, fim: time,
    ignorar_agendamento_id: Optional[UUID] = None, ignorar_grade_id: Optional[str] = None,
) -> dict:
    """Aulas (inclusive remanejadas para cá) e agendamentos ativos que ocupam o estúdio no horário."""
    aulas = [
        s for s in aulas_do_dia(db, data)
        if s["ocupa"] and s["estudio_efetivo"] == estudio_id and s["grade_id"] != ignorar_grade_id
        and sobrepoe(inicio, fim, s["inicio"], s["fim"])
    ]
    agendamentos = [
        a for a in agendamentos_ativos_do_estudio(db, data, estudio_id, ignorar_agendamento_id)
        if sobrepoe(inicio, fim, a.horario_inicio, a.horario_fim)
    ]
    return {"aulas": aulas, "agendamentos": agendamentos}


def descrever_aula(s: dict) -> str:
    return f"{hm(s['inicio'])}–{hm(s['fim'])} · {s['disciplina'] or 'Aula'} ({s['turma']})"


def descrever_agendamento(a: AgendamentoEstudio) -> str:
    return f"{hm(a.horario_inicio)}–{hm(a.horario_fim)} · {a.titulo}"


def avisos_agendamento(
    db: Session, data: date, estudio_id: int, inicio: time, fim: time,
    professor: Optional[str], turma_id: Optional[UUID], ignorar_id: Optional[UUID] = None,
) -> List[str]:
    """
    O que já está cadastrado e esbarra no agendamento sem ser choque no
    próprio estúdio: horário trancado, margem de segurança antes da próxima
    aula, professor ou turma ocupados em outro estúdio e relatório de aula já
    registrado nesse estúdio/horário. Pede confirmação, não bloqueia.
    """
    from app.services.agenda_conferencia import chave_estudio, relatorios_de_aula
    from app.services.idr_txt_parser import norm_key

    avisos: List[str] = []
    nomes = {e.id: e.nome for e in db.query(Estudio).all()}

    for b in bloqueios_do_dia(db, data).get(estudio_id, []):
        if sobrepoe(inicio, fim, b.horario_inicio, b.horario_fim):
            if eh_sob_demanda(b):
                minimo = b.minimo_aulas or MINIMO_AULAS_SOB_DEMANDA
                avisos.append(f"Horário sob demanda no {nomes.get(estudio_id)} ({hm(b.horario_inicio)}–"
                              f"{hm(b.horario_fim)}): só abre com no mínimo {minimo} aulas, porque o diretor "
                              f"precisa ser chamado. Confirme com a direção.")
            else:
                avisos.append(f"Horário trancado no {nomes.get(estudio_id)} das {hm(b.horario_inicio)} às "
                              f"{hm(b.horario_fim)}{(': ' + b.motivo) if b.motivo else ''}.")

    iv = intervalos_do_dia(db, data, [estudio_id]).get((turno_do_horario(inicio), estudio_id))
    if iv and sobrepoe(inicio, fim, parse_hora(iv["inicio"]), parse_hora(iv["fim"])):
        avisos.append(f"Pega o intervalo do {nomes.get(estudio_id)} ({iv['inicio']}–{iv['fim']}).")

    aulas = aulas_do_dia(db, data)
    fim_min = minutos(fim)
    for s in aulas:
        if s["ocupa"] and s["estudio_efetivo"] == estudio_id:
            ini_aula = minutos(s["inicio"])
            if fim_min <= ini_aula < fim_min + MARGEM_SEGURANCA_MIN:
                avisos.append(f"Termina a menos de {MARGEM_SEGURANCA_MIN} min da próxima aula do estúdio "
                              f"({descrever_aula(s)}) — sem margem de segurança.")

    prof_key = norm_key(professor) if professor else ""
    for s in aulas:
        if not s["ocupa"] or s["estudio_efetivo"] == estudio_id:
            continue
        if not sobrepoe(inicio, fim, s["inicio"], s["fim"]):
            continue
        onde = f"{nomes.get(s['estudio_efetivo'], 'outro estúdio')} ({descrever_aula(s)})"
        if prof_key and s["professor"] and norm_key(s["professor"]) == prof_key:
            avisos.append(f"O professor {s['professor']} tem aula da grade nesse horário: {onde}.")
        if turma_id and s["turma_id"] == str(turma_id):
            avisos.append(f"A turma {s['turma']} tem aula da grade nesse horário: {onde}.")
    if prof_key:
        outros = db.query(AgendamentoEstudio).filter(
            AgendamentoEstudio.data == data,
            AgendamentoEstudio.estudio_id != estudio_id,
            AgendamentoEstudio.status == STATUS_AGENDADO,
            ~AgendamentoEstudio.tipo.in_(OCORRENCIAS_DE_AULA),
        )
        if ignorar_id:
            outros = outros.filter(AgendamentoEstudio.id != ignorar_id)
        for a in outros.all():
            if a.professor and norm_key(a.professor) == prof_key and sobrepoe(inicio, fim, a.horario_inicio, a.horario_fim):
                avisos.append(f"O professor {a.professor} já está agendado nesse horário em "
                              f"{nomes.get(a.estudio_id, 'outro estúdio')}: {descrever_agendamento(a)}.")
    k_est = chave_estudio(nomes.get(estudio_id))
    for r in relatorios_de_aula(db, data):
        if chave_estudio(r.estudio) != k_est or not (r.start_time and r.end_time):
            continue
        if sobrepoe(inicio, fim, r.start_time, r.end_time):
            turma_txt = turma_label(r.turma) if r.turma else ""
            disc_txt = r.disciplina.nome if r.disciplina else ""
            avisos.append(f"Já existe relatório de aula registrado nesse estúdio e horário: {turma_txt} · "
                          f"{disc_txt} · {hm(r.start_time)}–{hm(r.end_time)} ({r.status}).")
    return avisos


# ─── Horários disponíveis (o "verde" da planilha) ─────────────────────

def horarios_livres(
    ocupados: List[Tuple[int, int]], janela: Tuple[int, int],
    bloqueados: Optional[List[Tuple[int, int]]] = None,
    duracao_minima: int = DURACAO_MINIMA_MIN, margem: int = MARGEM_SEGURANCA_MIN,
) -> List[Tuple[int, int]]:
    """
    Espaços livres dentro da janela (em minutos) onde cabe um agendamento:
    cada aula/agendamento é antecedido pela margem de segurança; horários
    trancados entram como estão; só vale espaço com pelo menos `duracao_minima`.
    """
    ini_j, fim_j = janela
    blocos = [(max(0, a - margem), b) for a, b in ocupados] + list(bloqueados or [])
    blocos = sorted((a, b) for a, b in blocos if b > ini_j and a < fim_j)
    livres, cursor = [], ini_j
    for a, b in blocos:
        if a > cursor:
            livres.append((cursor, min(a, fim_j)))
        cursor = max(cursor, b)
    if cursor < fim_j:
        livres.append((cursor, fim_j))
    return [(a, b) for a, b in livres if b - a >= duracao_minima]


# ─── Aulas que podem ter saído da grade ───────────────────────────────

def aulas_sem_registro_recente(db: Session, data: date, aulas: List[dict]) -> List[dict]:
    """
    Aulas previstas que não tiveram relatório de aula nenhuma vez nas últimas
    semanas, embora a turma tivesse outros relatórios no mesmo dia — sinal de
    que a aula saiu da grade do pedagógico (ex.: Clube de Leitura) e a grade
    do sistema não foi atualizada.
    """
    from app.services.agenda_conferencia import casar_relatorios, relatorios_de_aula

    hoje = date.today()
    alvo = {s["grade_id"]: s for s in aulas if not s["gravacao_sem_horario"] and s["tipo_slot"] == "aula"}
    contagem = {g: {"vistas": 0, "com_relatorio": 0} for g in alvo}
    for semanas in range(1, SEMANAS_SEM_REGISTRO + 1):
        dia = data - timedelta(days=7 * semanas)
        if dia >= hoje:
            continue
        slots_dia = grade_do_dia(db, dia)
        relatorios = relatorios_de_aula(db, dia)
        turmas_com_relatorio = {str(r.turma_id) for r in relatorios}
        casados, _ = casar_relatorios(slots_dia, relatorios)
        canceladas = set(grade_ids_cancelados(db, dia))
        for s in slots_dia:
            g = s["grade_id"]
            if g not in contagem or g in canceladas or s["turma_id"] not in turmas_com_relatorio:
                continue
            contagem[g]["vistas"] += 1
            if g in casados:
                contagem[g]["com_relatorio"] += 1
    return [
        alvo[g] for g, c in contagem.items()
        if c["vistas"] >= 2 and c["com_relatorio"] == 0
    ]


# ─── Montagem do dia ──────────────────────────────────────────────────

def _item_aula(s: dict, relatorio: Optional[dict], nomes: Dict[int, str], fantasma: bool = False) -> dict:
    o = s["ocorrencia"]
    canal = (o.canal.nome if o and o.canal else None) if s["remanejada"] else None
    return {
        "tipo": "AULA",
        "tipo_label": "Gravação da grade" if s["tipo_slot"] == "gravacao" else "Aula da grade",
        "cor": None,
        "gravacao": s["tipo_slot"] == "gravacao",
        "horario_mudou": s.get("horario_mudou", False),
        "inicio_grade": hm(s["inicio_grade"]) if s.get("inicio_grade") else None,
        "fim_grade": hm(s["fim_grade"]) if s.get("fim_grade") else None,
        "grade_id": s["grade_id"],
        "agendamento_id": str(o.id) if o else None,
        "inicio": hm(s["inicio"]),
        "fim": hm(s["fim"]),
        "titulo": s["disciplina"] or "Aula",
        "professor": s["professor"],
        "turma": s["turma"],
        "turma_id": s["turma_id"],
        "disciplina_id": s.get("disciplina_id"),
        "professor_id": s.get("professor_id"),
        "canal": canal or s["canal"],
        "canal_grade": s["canal"],
        "ordinal": s["ordinal"],
        "cancelada": s["cancelada"],
        "remanejada": s["remanejada"],
        # fantasma: o lugar original de uma aula que foi remanejada (não ocupa o estúdio)
        "fantasma": fantasma,
        "remanejada_para": nomes.get(s["estudio_efetivo"]) if s["remanejada"] else None,
        "remanejada_de": nomes.get(s["estudio_id"]) if s["remanejada"] else None,
        "estudio_grade_id": s["estudio_id"],
        "motivo_cancelamento": o.descricao if o else None,
        "chamado": o.chamado if o else None,
        "chamado_link": o.chamado_link if o else None,
        "relatorio": relatorio,
    }


def _item_agendamento(a: AgendamentoEstudio) -> dict:
    d = agendamento_to_dict(a)
    return {
        "tipo": a.tipo,
        "tipo_label": d["tipo_label"],
        "cor": d["cor"],
        "grade_id": None,
        "agendamento_id": d["id"],
        "inicio": d["horario_inicio"],
        "fim": d["horario_fim"],
        "titulo": a.titulo,
        "professor": a.professor,
        "turma": d["turma"],
        "turma_id": d["turma_id"],
        "descricao": a.descricao,
        "canal": d["canal"],
        "departamento": a.departamento,
        "ordinal": None,
        "cancelada": a.status == STATUS_CANCELADO,
        "remanejada": False,
        "fantasma": False,
        "chamado": a.chamado,
        "chamado_link": a.chamado_link,
        "relatorio": None,
        "registro": d,  # dados completos para o formulário de edição
    }


def _aviso(nivel: str, categoria: str, mensagem: str, **extra) -> dict:
    return {"nivel": nivel, "categoria": categoria, "mensagem": mensagem, **extra}


def _ocupa(it: dict) -> bool:
    return not it["cancelada"] and not it["fantasma"]


def montar_agenda_dia(db: Session, data: date) -> dict:
    from app.services.agenda_conferencia import (
        casar_relatorios, chave_estudio, diretores_com_relatorio, relatorios_de_aula, resumo_relatorio,
    )

    estudios = estudios_ativos(db)
    por_id = {e.id: e for e in estudios}
    todos_estudios = {e.id: e for e in db.query(Estudio).all()}
    nomes = {i: e.nome for i, e in todos_estudios.items()}
    _, duplicados = grade_do_dia_detalhado(db, data)
    aulas = aulas_do_dia(db, data)
    escala = escala_do_dia(db, data)
    transmissao = transmissao_do_dia(db, data)
    bloqueios = bloqueios_do_dia(db, data)
    intervalos = intervalos_do_dia(db, data, list(por_id))
    agendamentos = (
        db.query(AgendamentoEstudio)
        .filter(AgendamentoEstudio.data == data, ~AgendamentoEstudio.tipo.in_(OCORRENCIAS_DE_AULA))
        .order_by(AgendamentoEstudio.horario_inicio)
        .all()
    )
    conferencia: List[dict] = []
    hoje = date.today()
    feriado = feriado_do_dia(db, data)
    observacoes = observacoes_do_dia(db, data)
    if feriado:
        conferencia.append(_aviso("info", "feriado", f"Feriado: {feriado.nome}. A agenda deste dia fica "
                                  "trancada — nada pode ser agendado, remanejado ou cancelado."))

    # Registros reais do dia (só faz sentido até hoje)
    passado = data <= hoje
    relatorios = relatorios_de_aula(db, data) if passado else []
    casados, relatorios_soltos = casar_relatorios(aulas, relatorios)
    idr = diretores_com_relatorio(db, data) if passado else {}

    # (turno, estudio_id) → itens
    itens: Dict[Tuple[str, int], List[dict]] = {}
    turmas_col: Dict[Tuple[str, int], List[str]] = {}
    sem_horario = []
    gravacoes_sem_estudio: Dict[str, List[dict]] = {}
    for s in aulas:
        if s["gravacao_sem_horario"]:
            sem_horario.append({
                "grade_id": s["grade_id"], "turma": s["turma"], "disciplina": s["disciplina"],
                "professor": s["professor"], "estudio_id": s["estudio_id"],
            })
            continue
        rotulo_aula = f"{s['turma']} · {s['disciplina'] or 'Aula'} · {hm(s['inicio'])}–{hm(s['fim'])}"
        if not s["estudio_efetivo"] and s["tipo_slot"] == "gravacao":
            # Gravação da grade (MP) sem estúdio: aparece na faixa "a encaixar" do turno, para o chefe
            # arrastar para um estúdio (e ajustar o horário) só neste dia
            gravacoes_sem_estudio.setdefault(turno_do_horario(s["inicio"]), []).append({
                **_item_aula(s, None, nomes),
                "observacoes": observacoes.get(f"g:{s['grade_id']}", []),
            })
            continue
        if not s["estudio_efetivo"]:
            conferencia.append(_aviso("aviso", "grade", f"Aula da grade sem estúdio definido: {rotulo_aula}. "
                                      "Ela não aparece na agenda — defina o estúdio na Grade Horária."))
            continue
        if s["estudio_efetivo"] not in por_id:
            est = todos_estudios.get(s["estudio_efetivo"])
            conferencia.append(_aviso("aviso", "grade", f"Aula em estúdio inativo "
                                      f"({est.nome if est else s['estudio_efetivo']}): {rotulo_aula}."))
            continue
        rel = casados.get(s["grade_id"])
        est = por_id[s["estudio_efetivo"]]
        turno = turno_do_horario(s["inicio"])
        if fora_do_funcionamento(est, s["inicio"], s["fim"]):
            conferencia.append(_aviso("aviso", "grade", f"{est.nome}: aula fora do horário de funcionamento do "
                                      f"estúdio ({hm(est.horario_inicio)}–{hm(est.horario_fim)}): {rotulo_aula}."))
        if rel and s["cancelada"]:
            conferencia.append(_aviso("aviso", "relatorio", f"Aula marcada como cancelada, mas tem relatório de aula "
                                      f"registrado ({rel.status}): {rotulo_aula}."))
        if rel and rel.estudio and chave_estudio(rel.estudio) != chave_estudio(est.nome):
            quem = "a agenda (remanejada)" if s["remanejada"] else "a grade"
            conferencia.append(_aviso("aviso", "relatorio", f"Relatório de aula diz {rel.estudio}, {quem} diz "
                                      f"{est.nome}: {rotulo_aula}."))
        item = _item_aula(s, resumo_relatorio(rel) if rel else None, nomes)
        item["observacoes"] = observacoes.get(f"g:{s['grade_id']}", [])
        # Aula remanejada aparece só no estúdio de destino (sem marca no de origem, para não confundir)
        itens.setdefault((turno, s["estudio_efetivo"]), []).append(item)
        chave_turmas = (turno, s["estudio_id"] if s["estudio_id"] in por_id else s["estudio_efetivo"])
        rotulo = s["turma"] + (f" · {s['canal']}" if s["canal"] else "")
        if rotulo not in turmas_col.setdefault(chave_turmas, []):
            turmas_col[chave_turmas].append(rotulo)
    for d in duplicados:
        conferencia.append(_aviso("aviso", "grade", f"Aula repetida na grade (mesma turma, disciplina, estúdio e "
                                  f"horário): {d['turma']} · {d['disciplina'] or 'Aula'} · "
                                  f"{hm(d['inicio'])}–{hm(d['fim'])}. Aparece uma vez só na agenda."))

    for a in agendamentos:
        if a.estudio_id not in por_id:
            conferencia.append(_aviso("aviso", "agendamento", f"Agendamento em estúdio inativo: "
                                      f"{descrever_agendamento(a)}."))
            continue
        item = _item_agendamento(a)
        item["observacoes"] = observacoes.get(f"a:{a.id}", [])
        itens.setdefault((turno_do_horario(a.horario_inicio), a.estudio_id), []).append(item)
        if a.status == STATUS_AGENDADO and fora_do_funcionamento(por_id[a.estudio_id], a.horario_inicio, a.horario_fim):
            conferencia.append(_aviso("aviso", "agendamento", f"{por_id[a.estudio_id].nome}: agendamento fora do "
                                      f"horário de funcionamento do estúdio: {descrever_agendamento(a)}."))

    # Cancelamentos/remanejamentos de aulas que não estão mais na grade (grade mudou depois)
    ids_aulas = {s["grade_id"] for s in aulas}
    for o in db.query(AgendamentoEstudio).filter(
        AgendamentoEstudio.data == data, AgendamentoEstudio.tipo.in_(OCORRENCIAS_DE_AULA),
    ).all():
        if not o.grade_id or str(o.grade_id) not in ids_aulas:
            oque = "Cancelamento" if o.tipo == AULA_CANCELADA else "Remanejamento"
            conferencia.append(_aviso("info", "cancelamento", f"{oque} de uma aula que não está mais na grade: "
                                      f"{o.titulo} {hm(o.horario_inicio)}–{hm(o.horario_fim)}.",
                                      agendamento_id=str(o.id)))

    # Ocupação do dia inteiro por estúdio (para os horários disponíveis)
    ocupacao: Dict[int, List[Tuple[int, int]]] = {}
    for (turno, est_id), its in itens.items():
        for it in its:
            if _ocupa(it):
                ocupacao.setdefault(est_id, []).append((minutos(parse_hora(it["inicio"])), minutos(parse_hora(it["fim"]))))
    mostrar_livres = data >= hoje and not feriado

    turnos = []
    resumo = {"aulas": 0, "aulas_canceladas": 0, "aulas_remanejadas": 0, "agendamentos": 0,
              "agendamentos_cancelados": 0, "estudios_sem_diretor": 0, "estudios_em_uso": 0,
              "horarios_disponiveis": 0, "aulas_com_relatorio": 0, "aulas_sem_relatorio": 0,
              "conferir_relatorios": passado}
    for chave_turno, rotulo, ini_padrao, fim_padrao in TURNOS:
        colunas = []
        ini_min, fim_max = minutos(ini_padrao), minutos(fim_padrao)
        diretores_no_turno: Dict[str, List[str]] = {}
        for e in estudios:
            its = sorted(itens.get((chave_turno, e.id), []), key=lambda x: x["inicio"])
            for it in its:
                ini_min = min(ini_min, minutos(parse_hora(it["inicio"])))
                fim_max = max(fim_max, minutos(parse_hora(it["fim"])))
                if it["fantasma"]:
                    continue
                if it["tipo"] == "AULA":
                    if it["cancelada"]:
                        resumo["aulas_canceladas"] += 1
                    else:
                        resumo["aulas"] += 1
                        resumo["aulas_remanejadas"] += 1 if it["remanejada"] else 0
                        if passado:
                            resumo["aulas_com_relatorio" if it["relatorio"] else "aulas_sem_relatorio"] += 1
                else:
                    resumo["agendamentos_cancelados" if it["cancelada"] else "agendamentos"] += 1

            # Choques dentro do mesmo estúdio (o que está valendo não pode se sobrepor)
            validos = [it for it in its if _ocupa(it)]
            for i, x in enumerate(validos):
                for y in validos[i + 1:]:
                    if parse_hora(y["inicio"]) < parse_hora(x["fim"]) and parse_hora(x["inicio"]) < parse_hora(y["fim"]):
                        conferencia.append(_aviso(
                            "erro", "choque",
                            f"{e.nome} ({rotulo}): dois usos no mesmo horário — "
                            f"{x['inicio']}–{x['fim']} {x['titulo']} ({x.get('turma') or x['tipo_label']}) e "
                            f"{y['inicio']}–{y['fim']} {y['titulo']} ({y.get('turma') or y['tipo_label']}).",
                            turno=chave_turno, estudio_id=e.id))

            # Horários trancados e disponíveis desta coluna
            bloq_col = [
                {"inicio": hm(b.horario_inicio), "fim": hm(b.horario_fim), "motivo": b.motivo,
                 "tipo": b.tipo or BLOQUEIO_TRANCADO,
                 "minimo_aulas": (b.minimo_aulas or MINIMO_AULAS_SOB_DEMANDA) if eh_sob_demanda(b) else None}
                for b in bloqueios.get(e.id, [])
                if sobrepoe(b.horario_inicio, b.horario_fim, ini_padrao, fim_padrao)
            ]
            intervalo = intervalos.get((chave_turno, e.id))
            livres = []
            if mostrar_livres:
                janela = (minutos(ini_padrao), minutos(fim_padrao))
                if not e.funciona_24h and e.horario_inicio and e.horario_fim:
                    janela = (max(janela[0], minutos(e.horario_inicio)), min(janela[1], minutos(e.horario_fim)))
                if janela[1] > janela[0]:
                    # Trancado tira o horário do verde; sob demanda continua verde, com o aviso
                    bloq_min = [(minutos(b.horario_inicio), minutos(b.horario_fim))
                                for b in bloqueios.get(e.id, []) if not eh_sob_demanda(b)]
                    if intervalo:  # intervalo não conta como horário disponível
                        bloq_min.append((minutos(parse_hora(intervalo["inicio"])), minutos(parse_hora(intervalo["fim"]))))
                    demanda = [b for b in bloqueios.get(e.id, []) if eh_sob_demanda(b)]
                    for a, b in horarios_livres(ocupacao.get(e.id, []), janela, bloq_min):
                        sob = next((d for d in demanda if minutos(d.horario_inicio) < b and a < minutos(d.horario_fim)), None)
                        livre = {"inicio": hora_de_min(a), "fim": hora_de_min(b)}
                        if sob:
                            livre.update(sob_demanda=True,
                                         minimo_aulas=sob.minimo_aulas or MINIMO_AULAS_SOB_DEMANDA)
                        livres.append(livre)
                    resumo["horarios_disponiveis"] += len(livres)

            diretor = escala.get((chave_turno, e.id))
            em_uso = bool(validos)
            tem_diretor = bool(diretor and diretor.get("diretor_id") and diretor.get("ativo"))
            for _id, nome_troca in diretores_do_turno(diretor)[1:]:
                if nome_troca:
                    diretores_no_turno.setdefault(nome_troca, []).append(e.nome)
            if diretor and diretor.get("diretor_id") and not diretor.get("ativo"):
                conferencia.append(_aviso("aviso", "diretor", f"{e.nome} ({rotulo}): o diretor escalado "
                                          f"({diretor['nome']}) está inativo no cadastro."))
            if em_uso:
                resumo["estudios_em_uso"] += 1
                if not tem_diretor and not feriado:
                    resumo["estudios_sem_diretor"] += 1
                    conferencia.append(_aviso("aviso", "diretor", f"{e.nome} ({rotulo}) tem uso e está sem diretor "
                                              "de imagem escalado.", turno=chave_turno, estudio_id=e.id))
            if tem_diretor:
                diretores_no_turno.setdefault(diretor["nome"], []).append(e.nome)

            fez_relatorio = idr.get((chave_turno, chave_estudio(e.nome)), [])
            escalados = {n for _i, n in diretores_do_turno(diretor)}
            if fez_relatorio and tem_diretor and not (escalados & set(fez_relatorio)):
                conferencia.append(_aviso("info", "diretor", f"{e.nome} ({rotulo}): escalado {diretor['nome']}, mas o "
                                          f"relatório de imagem foi feito por {', '.join(fez_relatorio)}."))
            colunas.append({
                "estudio_id": e.id,
                "estudio_nome": e.nome,
                "turmas": turmas_col.get((chave_turno, e.id), []),
                "diretor": diretor,
                "transmissao": transmissao.get((chave_turno, e.id)) or {"youtube_link": None, "chave_transmissao": None},
                "diretor_relatorio": fez_relatorio,
                "em_uso": em_uso,
                "itens": its,
                "livres": livres,
                "bloqueios": bloq_col,
                "intervalo": intervalo,
            })
        for nome, lista in diretores_no_turno.items():
            if len(lista) > 1:
                conferencia.append(_aviso("aviso", "diretor", f"{nome} está escalado em {len(lista)} estúdios ao "
                                          f"mesmo tempo no turno {rotulo}: {', '.join(lista)}."))
        turnos.append({
            "turno": chave_turno,
            "label": rotulo,
            "inicio": hora_de_min(ini_min),
            "fim": hora_de_min(fim_max),
            "estudios": colunas,
            "gravacoes_sem_estudio": sorted(gravacoes_sem_estudio.get(chave_turno, []), key=lambda x: x["inicio"]),
        })

    # Relatórios de aula que não casaram com nenhuma aula prevista
    for r in relatorios_soltos:
        k_est = chave_estudio(r.estudio)
        est_id = next((e.id for e in estudios if chave_estudio(e.nome) == k_est), None)
        coberto = bool(est_id and r.start_time and r.end_time and any(
            a.estudio_id == est_id and a.status == STATUS_AGENDADO
            and sobrepoe(a.horario_inicio, a.horario_fim, r.start_time, r.end_time)
            for a in agendamentos
        ))
        if not coberto:
            turma_txt = turma_label(r.turma) if getattr(r, "turma", None) else "turma?"
            disc_txt = r.disciplina.nome if getattr(r, "disciplina", None) else "disciplina?"
            conferencia.append(_aviso("info", "relatorio", f"Relatório de aula sem aula prevista nem agendamento na "
                                      f"agenda: {turma_txt} · {disc_txt} · {r.horario_aula} · {r.estudio} ({r.status})."))

    # Aulas que podem ter saído da grade do pedagógico
    for s in aulas_sem_registro_recente(db, data, [a for a in aulas if not a["cancelada"]]):
        conferencia.append(_aviso(
            "info", "grade_desatualizada",
            f"{s['turma']} · {s['disciplina'] or 'Aula'} · {hm(s['inicio'])}–{hm(s['fim'])}: nenhum relatório "
            f"de aula nas últimas {SEMANAS_SEM_REGISTRO} semanas, embora a turma tenha tido outras aulas "
            "registradas. Pode ter saído da grade — confirme com o pedagógico.",
            grade_id=s["grade_id"]))

    ordem_nivel = {"erro": 0, "aviso": 1, "info": 2}
    conferencia.sort(key=lambda c: ordem_nivel.get(c["nivel"], 3))
    resumo["inconsistencias"] = sum(1 for c in conferencia if c["nivel"] in ("erro", "aviso"))

    return {
        "data": data.isoformat(),
        "dia_semana": data.weekday(),
        "dia_semana_label": DIAS_SEMANA[data.weekday()],
        "turnos": turnos,
        "gravacoes_sem_horario": sem_horario,
        "conferencia": conferencia,
        "resumo": resumo,
        "feriado": {"id": feriado.id, "nome": feriado.nome} if feriado else None,
        "regras": {"duracao_minima": DURACAO_MINIMA_MIN, "margem_seguranca": MARGEM_SEGURANCA_MIN},
    }


def opcoes(db: Session) -> dict:
    estudios = estudios_ativos(db)
    cfg = config_estudios(db)
    diretores = (
        db.query(DiretorImagem).filter(DiretorImagem.is_active == True)  # noqa: E712
        .order_by(DiretorImagem.nome).all()
    )
    turmas = db.query(Turma).filter(Turma.is_active == True).all()  # noqa: E712
    canais = (
        db.query(CanalIptvModel).filter(CanalIptvModel.ativo == True)  # noqa: E712
        .order_by(CanalIptvModel.numero).all()
    )
    return {
        "estudios": [{
            "id": e.id, "nome": e.nome,
            "libras": bool(cfg.get(e.id) and cfg[e.id].libras),
            "prioridade_evento": cfg[e.id].prioridade_evento if cfg.get(e.id) else None,
        } for e in estudios],
        "diretores": [{"id": str(d.id), "nome": d.nome} for d in diretores],
        "turmas": sorted(
            [{"id": str(t.id), "nome": turma_label(t)} for t in turmas], key=lambda t: t["nome"] or ""
        ),
        "canais": [{"id": c.id, "nome": c.nome, "numero": c.numero} for c in canais],
        "professores": [p.nome for p in db.query(Professor).filter(Professor.is_active == True)  # noqa: E712
                        .order_by(Professor.nome).all()],
        "tipos": [{"valor": k, **v} for k, v in TIPOS_AGENDAMENTO.items()],
        "tipos_evento": list(TIPOS_DE_EVENTO),
        "textos_prontos": TEXTOS_PRONTOS,
        "cor_cancelado": COR_CANCELADO,
        "minimo_sob_demanda": MINIMO_AULAS_SOB_DEMANDA,
        "departamentos": DEPARTAMENTOS_SUGERIDOS,
        "turnos": [{"valor": k, "label": rotulo} for k, rotulo, _, _ in TURNOS],
        "dias_semana": [{"valor": i, "label": d} for i, d in enumerate(DIAS_SEMANA)],
        "regras": {"duracao_minima": DURACAO_MINIMA_MIN, "margem_seguranca": MARGEM_SEGURANCA_MIN},
    }


# ─── Sugestão de estúdio (remanejamento e eventos) ────────────────────

def sugerir_estudios(
    db: Session, data: date, inicio: time, fim: time, *, para: str = "aula",
    ignorar_grade_id: Optional[str] = None, ignorar_agendamento_id: Optional[UUID] = None,
    ocupados_extra: Optional[Dict[int, List[Tuple[time, time]]]] = None,
) -> List[dict]:
    """
    Estúdios para o horário, do mais indicado ao menos: livres primeiro; para
    evento, a prioridade definida pela direção (o Estúdio 9 costuma ser o
    primeiro); depois os preparados para Libras. `ocupados_extra` são usos que
    ainda não foram gravados (ex.: outras aulas sendo remanejadas junto).
    """
    cfg = config_estudios(db)
    bloqueios = bloqueios_do_dia(db, data)
    saida = []
    for ordem, e in enumerate(estudios_ativos(db)):
        motivo = None
        if fora_do_funcionamento(e, inicio, fim):
            motivo = f"funciona das {hm(e.horario_inicio)} às {hm(e.horario_fim)}"
        else:
            c = conflitos(db, data, e.id, inicio, fim, ignorar_agendamento_id, ignorar_grade_id)
            if c["aulas"]:
                motivo = "ocupado: " + descrever_aula(c["aulas"][0])
            elif c["agendamentos"]:
                motivo = "ocupado: " + descrever_agendamento(c["agendamentos"][0])
            elif any(sobrepoe(inicio, fim, a, b) for a, b in (ocupados_extra or {}).get(e.id, [])):
                motivo = "ocupado por outra aula remanejada agora"
            else:
                tranc = [b for b in bloqueios.get(e.id, [])
                         if not eh_sob_demanda(b) and sobrepoe(inicio, fim, b.horario_inicio, b.horario_fim)]
                if tranc:
                    motivo = "horário trancado" + (f" ({tranc[0].motivo})" if tranc[0].motivo else "")
        c_e = cfg.get(e.id)
        saida.append({
            "id": e.id, "nome": e.nome, "livre": motivo is None, "motivo": motivo,
            "libras": bool(c_e and c_e.libras),
            "prioridade_evento": c_e.prioridade_evento if c_e else None,
            "_ordem": ordem,
        })
    def chave(x):
        prioridade = x["prioridade_evento"] if (para == "evento" and x["prioridade_evento"]) else 99
        return (0 if x["livre"] else 1, prioridade, 0 if x["libras"] else 1, x["_ordem"])
    saida.sort(key=chave)
    for x in saida:
        x.pop("_ordem", None)
    return saida


# ─── Estúdio da aula para os relatórios ───────────────────────────────

def _numero_do_horario(texto: Optional[str]) -> Optional[int]:
    m = re.match(r"\s*(\d+)\s*º", texto or "")
    return int(m.group(1)) if m else None


def estudio_da_aula(
    db: Session, turma_id: UUID, data: date, *, horario_aula: Optional[str] = None,
    turno: Optional[str] = None, inicio: Optional[time] = None, disciplina_id: Optional[UUID] = None,
    agendamento_id: Optional[UUID] = None,
) -> dict:
    """
    Onde a aula acontece na data, pelo que o diretor-chefe definiu: o estúdio
    da grade ou, se a aula foi remanejada naquele dia, o estúdio de destino.
    O horário vem como hora de início ou como "2º Horário" (mesma numeração
    usada no relatório do diretor de imagem).
    """
    if agendamento_id is not None:
        # Aula marcada na Agenda (antecipada, reposição…) tem prioridade sobre a grade do mesmo horário
        ag = aula_da_agenda(db, turma_id, data, None, agendamento_id=agendamento_id)
        if ag:
            return ag
    aulas = [s for s in aulas_do_dia(db, data) if s["turma_id"] == str(turma_id) and not s["gravacao_sem_horario"]]
    alvo = None
    if inicio is None and horario_aula:
        if "às" in horario_aula or re.match(r"^\s*\d{1,2}:\d{2}", horario_aula):
            try:
                inicio = parse_hora(horario_aula.split("às")[0])
            except ValueError:
                inicio = None
        else:
            n = _numero_do_horario(horario_aula)
            if n:
                from app.services.image_director_slot import list_numbered_slots_for_day, slot_do_ordinal
                try:
                    numerados = list_numbered_slots_for_day(db, turma_id, data, turno)
                except Exception:
                    numerados = []
                g = slot_do_ordinal(numerados, n)
                if g:
                    alvo = next((s for s in aulas if s["grade_id"] == str(g.id)), None)
                    if alvo is None:
                        inicio = g.horario_inicio
    if alvo is None and inicio is not None:
        candidatos = [s for s in aulas if s["inicio"] == inicio] or [
            s for s in aulas if s.get("inicio_grade") == inicio] or [
            s for s in aulas if s["inicio"] <= inicio < s["fim"]]
        if disciplina_id and len(candidatos) > 1:
            candidatos = [s for s in candidatos if s["disciplina_id"] == str(disciplina_id)] or candidatos
        alvo = candidatos[0] if candidatos else None
    if alvo is None or not alvo["estudio_efetivo"]:
        # Fora da grade: aula marcada na Agenda para a turma (gravação antecipada, reposição, aula extra…)
        if inicio is not None:
            ag = aula_da_agenda(db, turma_id, data, inicio)
            if ag:
                return ag
        return {"encontrado": False}
    est = db.query(Estudio).filter(Estudio.id == alvo["estudio_efetivo"]).first()
    if not est:
        return {"encontrado": False}
    origem = db.query(Estudio).filter(Estudio.id == alvo["estudio_id"]).first() if alvo["remanejada"] else None
    o = alvo.get("ocorrencia")
    canal_dia = (o.canal.nome if o is not None and o.canal else None) if alvo["remanejada"] else None
    return {
        "encontrado": True,
        "estudio": est.nome,
        "estudio_id": est.id,
        "remanejada": alvo["remanejada"],
        "cancelada": alvo["cancelada"],
        "estudio_grade": origem.nome if origem else est.nome,
        "inicio": hm(alvo["inicio"]),
        "fim": hm(alvo["fim"]),
        "horario_faixa": f"{hm(alvo['inicio'])} às {hm(alvo['fim'])}",
        "ordinal": alvo.get("ordinal"),
        "turno": turno_do_horario(alvo["inicio"]),
        "disciplina": alvo["disciplina"],
        "disciplina_id": alvo.get("disciplina_id"),
        "professor": alvo.get("professor"),
        "professor_id": alvo.get("professor_id"),
        "canal": canal_dia or alvo.get("canal"),
        "chamado": o.chamado if o is not None else None,
        "grade_id": alvo["grade_id"],
        "antecipada": False,
        "solicitante_antecipacao": None,
        "data_referencia": None,
        "tipo_agenda": None,
        # Aula da grade que vai ao ar com uma gravação antecipada (o chefe ligou na Agenda)
        "exibicao_antecipada": exibicao_antecipada(db, data, alvo),
        # Aula da grade que foi reposta numa gravação em outro dia (o chefe ligou na Agenda)
        "reposicao_agendada": reposicao_agendada(db, data, alvo),
        **diretor_escalado(db, data, alvo["inicio"], est.id),
        **transmissao_da_aula(db, data, alvo["inicio"], est.id),
    }


def exibicao_antecipada(db: Session, data: date, slot: dict) -> Optional[dict]:
    """
    A aula da grade deste dia vai ao ar com uma gravação antecipada? O diretor-chefe liga a
    gravação (tipo Gravação antecipada) à aula da grade na Agenda: data da exibição + aula.
    Assim a exibição aponta para a gravação e não é lançada como uma segunda gravação.
    """
    ligada = _gravacao_ligada(db, data, slot, reposicao=False)
    if ligada is None:
        return None
    return {
        "agendamento_id": str(ligada.id),
        "data_gravacao": ligada.data.isoformat(),
        "estudio_gravacao": ligada.estudio.nome if ligada.estudio else None,
        "solicitante": ligada.solicitante_antecipacao,
        "chamado": ligada.chamado,
        "titulo": ligada.titulo,
    }


def _gravacao_ligada(db: Session, data: date, slot: dict, *, reposicao: bool):
    return db.query(AgendamentoEstudio).filter(
        AgendamentoEstudio.tipo.in_(TIPOS_GRAVACAO),
        AgendamentoEstudio.status == STATUS_AGENDADO,
        AgendamentoEstudio.data_referencia == data,
        AgendamentoEstudio.reposicao == reposicao,
        AgendamentoEstudio.grade_exibicao_id == UUID(slot["grade_id"]),
    ).first()


def reposicao_agendada(db: Session, data: date, slot: dict) -> Optional[dict]:
    """
    A aula da grade deste dia não aconteceu e foi reposta numa gravação em outro dia,
    ligada pelo diretor-chefe na Agenda (Gravação + Reposição + aula da grade).
    """
    g = _gravacao_ligada(db, data, slot, reposicao=True)
    if g is None:
        return None
    return {
        "agendamento_id": str(g.id),
        "data_gravacao": g.data.isoformat(),
        "estudio_gravacao": g.estudio.nome if g.estudio else None,
        "solicitante": g.solicitante_antecipacao,
        "chamado": g.chamado,
    }


def aulas_da_turma_no_dia(db: Session, turma_id: UUID, data: date) -> List[dict]:
    """Aulas da grade da turma na data (para o chefe escolher qual aula a gravação antecipada substitui)."""
    return [{
        "grade_id": s["grade_id"],
        "inicio": hm(s["inicio"]),
        "fim": hm(s["fim"]),
        "disciplina": s["disciplina"],
        "professor": s.get("professor"),
        "descricao": f"{hm(s['inicio'])}–{hm(s['fim'])} · {s['disciplina'] or 'Aula'}"
                     + (f" · {s['professor']}" if s.get("professor") else ""),
    } for s in sorted(aulas_do_dia(db, data), key=lambda x: x["inicio"])
        if s["turma_id"] == str(turma_id) and not s["gravacao_sem_horario"]]


def grade_semana_estudio(
    db: Session,
    estudio_id: int,
    data_inicio: date,
    data_fim: date,
) -> List[dict]:
    """
    Retorna todos os slots de um estúdio em um período (grade fixa das turmas vinculadas
    + agendamentos/eventos + cancelamentos/remanejamentos da Agenda).
    Usado na Grade Horária por Estúdio.
    """
    from app.models.class_report import ClassReport
    from app.models.image_director_report import ImageDirectorReport

    estudio = db.query(Estudio).filter(Estudio.id == estudio_id).first()
    if not estudio:
        return []

    DIAS_MAP = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"}
    resultado = []
    curr = data_inicio
    delta = timedelta(days=1)

    while curr <= data_fim:
        dia_semana_num = curr.weekday()
        dia_semana_nome = DIAS_MAP.get(dia_semana_num, "Segunda")
        escala = escala_do_dia(db, curr)
        
        reports_do_dia = db.query(ClassReport).filter(
            ClassReport.data_aula == curr,
            ClassReport.is_deleted == False
        ).all()

        idrs_do_dia = db.query(ImageDirectorReport).filter(
            ImageDirectorReport.data_relatorio == curr,
            ImageDirectorReport.is_deleted == False
        ).all()

        aulas = aulas_do_dia(db, curr)

        for s in aulas:
            afeta_estudio = (s["estudio_efetivo"] == estudio_id) or (
                s["estudio_id"] == estudio_id and (s["cancelada"] or s["remanejada"])
            )
            if not afeta_estudio:
                continue

            is_gravacao = s.get("gravacao_sem_horario", False)
            h_ini = s["inicio"].strftime("%H:%M") if s.get("inicio") else ""
            h_fim = s["fim"].strftime("%H:%M") if s.get("fim") else ""
            horario_label = "GRAVAÇÃO" if is_gravacao else f"{h_ini} às {h_fim}"
            turno = s.get("turno_aula") or (turno_do_horario(s["inicio"]) if s.get("inicio") else "manha")
            escala_item = escala.get((turno, estudio_id))
            diretor_nome = escala_item["nome"] if escala_item else None

            # Match de relatório de aula
            report_id = None
            report_status = None
            for r in reports_do_dia:
                if str(r.turma_id) == str(s["turma_id"]) and (
                    not s.get("disciplina_id") or str(r.disciplina_id) == str(s["disciplina_id"])
                ):
                    report_id = str(r.id)
                    report_status = r.status
                    break

            # Match de relatório do diretor de imagem
            idr_id = None
            idr_status = None
            for idr in idrs_do_dia:
                if str(idr.turma_id) == str(s["turma_id"]) or (report_id and str(idr.class_report_id) == str(report_id)):
                    idr_id = str(idr.id)
                    idr_status = idr.status
                    break

            tipo_slot = "aula"
            tipo_label = "Aula Regular"
            cor = None
            if s["cancelada"]:
                tipo_slot = "AULA_CANCELADA"
                tipo_label = "Aula cancelada"
                cor = COR_CANCELADO
            elif s["remanejada"]:
                tipo_slot = "AULA_REMANEJADA"
                if s["estudio_efetivo"] == estudio_id:
                    tipo_label = f"Remanejada (de {s.get('remanejada_de', 'outro estúdio')})"
                    cor = "#3b82f6"
                else:
                    tipo_label = f"Remanejada (para {s.get('remanejada_para', 'outro estúdio')})"
                    cor = "#64748b"

            resultado.append({
                "id": s["grade_id"],
                "grade_id": s["grade_id"],
                "data": curr.isoformat(),
                "dia_semana": dia_semana_nome,
                "horario_inicio": h_ini or None,
                "horario_fim": h_fim or None,
                "horario_label": horario_label,
                "is_gravacao": is_gravacao,
                "gravacao_grade": s.get("tipo_slot") == "gravacao",
                "tipo_slot": tipo_slot,
                "tipo_label": tipo_label,
                "cor": cor,
                "turma_id": s["turma_id"],
                "turma_nome": s["turma"] or "N/A",
                "turma_modalidade": s.get("turma_modalidade", "REGULAR"),
                "disciplina_id": s["disciplina_id"],
                "disciplina_nome": s["disciplina"] or "N/A",
                "professor_id": s.get("professor_id"),
                "professor_nome": s["professor"] or "N/A",
                "estudio_id": estudio_id,
                "estudio_nome": estudio.nome,
                "canal_iptv": s.get("canal"),
                "turno_aula": turno,
                "cancelada": s["cancelada"],
                "remanejada": s["remanejada"],
                "motivo_cancelamento": s.get("motivo_cancelamento"),
                "remanejada_para": s.get("remanejada_para"),
                "remanejada_de": s.get("remanejada_de"),
                "chamado": s.get("chamado"),
                "report_id": report_id,
                "report_status": report_status,
                "idr_id": idr_id,
                "idr_status": idr_status,
                "diretor_imagem_nome": diretor_nome,
            })

        # Agendamentos / Eventos / Gravações de estúdio
        agendamentos = db.query(AgendamentoEstudio).filter(
            AgendamentoEstudio.data == curr,
            AgendamentoEstudio.estudio_id == estudio_id,
            AgendamentoEstudio.status == STATUS_AGENDADO,
            ~AgendamentoEstudio.tipo.in_(OCORRENCIAS_DE_AULA)
        ).all()

        for a in agendamentos:
            h_ini = a.horario_inicio.strftime("%H:%M") if a.horario_inicio else ""
            h_fim = a.horario_fim.strftime("%H:%M") if a.horario_fim else ""
            horario_label = f"{h_ini} às {h_fim}"
            turno = turno_do_horario(a.horario_inicio) if a.horario_inicio else "manha"
            escala_item = escala.get((turno, estudio_id))
            diretor_nome = escala_item["nome"] if escala_item else None
            info = TIPOS_AGENDAMENTO.get(a.tipo, {})
            rotulo, cor = ROTULO_ESPECIAL.get(a.tipo, (info.get("label", a.tipo), info.get("cor", "#2563eb")))

            # Match de relatório se houver
            report_id = None
            report_status = None
            for r in reports_do_dia:
                if a.turma_id and str(r.turma_id) == str(a.turma_id):
                    report_id = str(r.id)
                    report_status = r.status
                    break

            resultado.append({
                "id": str(a.id),
                "agendamento_id": str(a.id),
                "grade_id": None,
                "data": curr.isoformat(),
                "dia_semana": dia_semana_nome,
                "horario_inicio": h_ini or None,
                "horario_fim": h_fim or None,
                "horario_label": horario_label,
                "is_gravacao": False,
                "tipo_slot": a.tipo,
                "tipo_label": rotulo,
                "cor": cor,
                "titulo": a.titulo,
                "nome_evento": a.nome_evento,
                "descricao": a.descricao,
                "departamento": a.departamento,
                "turma_id": str(a.turma_id) if a.turma_id else None,
                "turma_nome": a.turma.nomenclatura_padrao or a.turma.nome if a.turma else (a.titulo or rotulo),
                "turma_modalidade": a.turma.modalidade if a.turma else "REGULAR",
                "disciplina_id": None,
                "disciplina_nome": a.nome_evento or a.titulo or rotulo,
                "professor_id": None,
                "professor_nome": a.professor or "N/A",
                "estudio_id": estudio_id,
                "estudio_nome": estudio.nome,
                "canal_iptv": a.canal.nome if a.canal else None,
                "turno_aula": turno,
                "cancelada": False,
                "remanejada": False,
                "motivo_cancelamento": None,
                "chamado": a.chamado,
                "chamado_link": a.chamado_link,
                "chave_transmissao": a.chave_transmissao,
                "report_id": report_id,
                "report_status": report_status,
                "idr_id": None,
                "idr_status": None,
                "diretor_imagem_nome": diretor_nome,
            })

        curr += delta

    return resultado

def diretor_escalado(db: Session, data: date, inicio: time, estudio_id: int) -> dict:
    """Diretor de imagem escalado no estúdio e turno (escala diária); o segundo, se já assumiu."""
    e = escala_do_dia(db, data).get((turno_do_horario(inicio), estudio_id))
    if not e:
        return {"diretor_imagem_id": None, "diretor_nome": None}
    atual = {"diretor_imagem_id": e.get("diretor_id"), "diretor_nome": e.get("nome")}
    for t in sorted(e.get("trocas", []), key=lambda x: x.get("a_partir") or "99:99"):
        if t.get("a_partir") and hm(inicio) >= t["a_partir"]:
            atual = {"diretor_imagem_id": t["diretor_id"], "diretor_nome": t.get("nome")}
    return atual


def aula_da_agenda(db: Session, turma_id: UUID, data: date, inicio: Optional[time],
                   agendamento_id: Optional[UUID] = None) -> Optional[dict]:
    """Aula da turma marcada na Agenda fora da grade, no horário informado (ou pelo id do agendamento)."""
    for a in agendamentos_de_aula_da_turma(db, turma_id, data, data):
        if agendamento_id is not None:
            casa = str(a.id) == str(agendamento_id)
        else:
            casa = inicio is not None and a.horario_inicio <= inicio < a.horario_fim
        if casa:
            return {
                "encontrado": True,
                "estudio": a.estudio.nome if a.estudio else None,
                "estudio_id": a.estudio_id,
                "remanejada": False,
                "cancelada": False,
                "estudio_grade": None,
                "inicio": hm(a.horario_inicio),
                "fim": hm(a.horario_fim),
                "horario_faixa": f"{hm(a.horario_inicio)} às {hm(a.horario_fim)}",
                "ordinal": None,
                "turno": turno_do_horario(a.horario_inicio),
                "disciplina": a.titulo,
                "disciplina_id": None,
                "professor": a.professor,
                "professor_id": None,
                "canal": a.canal.nome if a.canal else None,
                "grade_id": None,
                # gravação (qualquer uma): o diretor registra como "Aula gravada"
                "antecipada": a.tipo in TIPOS_GRAVACAO,
                "gravacao": a.tipo in TIPOS_GRAVACAO,
                "reposicao": bool(getattr(a, "reposicao", False)) or a.tipo == "REPOSICAO",
                "solicitante_antecipacao": a.solicitante_antecipacao,
                "data_referencia": a.data_referencia.isoformat() if a.data_referencia else None,
                "motivo_referencia": a.motivo_referencia,
                "chamado": a.chamado,
                "tipo_agenda": a.tipo,
                "tipo_agenda_label": TIPOS_AGENDAMENTO.get(a.tipo, {}).get("label", a.tipo),
                "agendamento_id": str(a.id),
                **diretor_escalado(db, data, a.horario_inicio, a.estudio_id),
                **transmissao_da_aula(db, data, a.horario_inicio, a.estudio_id),
            }
    return None


def agendamentos_de_aula_da_turma(db: Session, turma_id: UUID, data_inicio: date, data_fim: date):
    return (
        db.query(AgendamentoEstudio)
        .filter(
            AgendamentoEstudio.turma_id == turma_id,
            AgendamentoEstudio.data >= data_inicio,
            AgendamentoEstudio.data <= data_fim,
            AgendamentoEstudio.tipo.in_(TIPOS_DE_AULA),
            AgendamentoEstudio.status == STATUS_AGENDADO,
        )
        .order_by(AgendamentoEstudio.data, AgendamentoEstudio.horario_inicio)
        .all()
    )


def semana_da_turma(db: Session, turma_id: UUID, data_inicio: date, data_fim: date) -> dict:
    """
    Para a Grade Horária da turma: aulas remanejadas/canceladas no dia (estúdio do dia)
    e aulas da Agenda fora da grade (antecipada, reposição, aula extra…).
    """
    ocorrencias = []
    for o in (
        db.query(AgendamentoEstudio)
        .join(Grade, Grade.id == AgendamentoEstudio.grade_id)
        .filter(
            Grade.turma_id == turma_id,
            AgendamentoEstudio.data >= data_inicio,
            AgendamentoEstudio.data <= data_fim,
            AgendamentoEstudio.tipo.in_(OCORRENCIAS_DE_AULA),
        )
        .all()
    ):
        ocorrencias.append({
            "grade_id": str(o.grade_id),
            "data": o.data.isoformat(),
            "tipo": o.tipo,
            "estudio_id": o.estudio_id,
            "estudio_nome": o.estudio.nome if o.estudio else None,
        })
    extras = [{
        "id": str(a.id),
        "data": a.data.isoformat(),
        "tipo": a.tipo,
        "tipo_label": TIPOS_AGENDAMENTO.get(a.tipo, {}).get("label", a.tipo),
        "titulo": a.titulo,
        "professor": a.professor,
        "inicio": hm(a.horario_inicio),
        "fim": hm(a.horario_fim),
        "estudio_nome": a.estudio.nome if a.estudio else None,
        "turno": turno_do_horario(a.horario_inicio),
        "chamado": a.chamado,
        "reposicao": bool(getattr(a, "reposicao", False)) or a.tipo == "REPOSICAO",
        "data_referencia": a.data_referencia.isoformat() if a.data_referencia else None,
    } for a in agendamentos_de_aula_da_turma(db, turma_id, data_inicio, data_fim)]
    # Diretor escalado por dia/turno/estúdio (para mostrar o responsável pela aula)
    linhas_esc = _linhas_escala_periodo(db, data_inicio, data_fim)
    nomes_esc = _nomes_diretores(db, {t["diretor_imagem_id"] for e in linhas_esc for t in e.trocas()})
    escala = [{
        "data": e.data.isoformat(),
        "turno": e.turno,
        "estudio_id": e.estudio_id,
        "diretor": e.diretor.nome if e.diretor else None,
        "diretor2": e.diretor2.nome if e.diretor2 else None,
        "troca_horario": hm(e.troca_horario),
        "trocas": [{"diretor": nomes_esc.get(t["diretor_imagem_id"]), "a_partir": t.get("a_partir")} for t in e.trocas()],
    } for e in linhas_esc]
    return {"ocorrencias": ocorrencias, "extras": extras, "escala": escala}


def _linhas_escala_periodo(db: Session, data_inicio: date, data_fim: date):
    return db.query(EscalaDiaEstudio).filter(
        EscalaDiaEstudio.data >= data_inicio, EscalaDiaEstudio.data <= data_fim,
        EscalaDiaEstudio.diretor_imagem_id.isnot(None),
    ).all()


def minha_escala(db: Session, data: date, diretor_id: UUID) -> dict:
    """
    Grade do diretor de imagem: os estúdios e turnos em que ele está escalado no dia,
    com o que acontece em cada um (aulas da grade, remanejadas, eventos) e o link/chave
    da transmissão.
    """
    agenda = montar_agenda_dia(db, data)
    alvo = str(diretor_id)
    turnos = []
    for t in agenda["turnos"]:
        estudios = []
        for c in t["estudios"]:
            d = c.get("diretor") or {}
            if alvo not in {i for i, _n in diretores_do_turno(d)}:
                continue
            estudios.append({
                "estudio_id": c["estudio_id"],
                "estudio_nome": c["estudio_nome"],
                "turmas": c.get("turmas", []),
                "diretor": d.get("nome"),
                "diretor2": d.get("nome2"),
                "troca_horario": d.get("troca_horario"),
                "trocas": d.get("trocas", []),
                "youtube_link": (c.get("transmissao") or {}).get("youtube_link"),
                "chave_transmissao": (c.get("transmissao") or {}).get("chave_transmissao"),
                "itens": [i for i in c["itens"] if not i.get("fantasma")],
            })
        if estudios:
            turnos.append({"turno": t["turno"], "label": t["label"], "inicio": t["inicio"], "fim": t["fim"],
                           "estudios": estudios})
    return {"data": agenda["data"], "dia_semana_label": agenda["dia_semana_label"],
            "feriado": agenda.get("feriado"), "turnos": turnos}
