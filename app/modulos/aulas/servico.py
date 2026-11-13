"""
Canal Educação v5 — A Aula: geração, ligação com os relatórios e status.

Fonte de cada aula do dia (mesma regra da Agenda e da Auditoria, para os
números baterem):

1. a grade vigente do dia (`agenda_estudios.aulas_do_dia`): já vem com o
   cancelamento e o remanejamento lançados na Agenda;
2. as gravações e aulas extras marcadas na Agenda para uma turma;
3. relatório de aula que não casou com nenhuma das duas (vira aula
   "relatorio", para nada ficar de fora da conferência).

O relatório de aula do assistente casa com a aula pela mesma regra da Agenda
(`agenda_conferencia.casar_relatorios`: turma + disciplina + horário). O
relatório do diretor é ligado pela aula do turno (`image_director_lessons.class_report_id`)
ou, na falta, pelo turno + estúdio do dia.

Recalcular é barato e idempotente. Para não recalcular o que não mudou, cada
dia guarda uma assinatura dos dados de origem (AulaSincronizacao).
"""

from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import aula as A
from app.models.agenda_estudio import AgendamentoEstudio, FeriadoAgenda
from app.models.auxiliares import Disciplina, Grade, Professor
from app.models.class_report import ClassReport
from app.models.image_director_report import ImageDirectorLesson, ImageDirectorReport
from app.models.infraestrutura import Estudio, GradeVersao
from app.models.turma import Turma

MAX_DIAS = 62  # maior período que a tela pede de uma vez

STATUS_ROTULO = {
    A.PREVISTA: "Prevista",
    A.SEM_RELATORIO: "Sem relatório",
    A.EM_RELATORIO: "Relatório em rascunho",
    A.DEVOLVIDA: "Devolvida para correção",
    A.AGUARDANDO_VALIDACAO: "Aguardando validação",
    A.AGUARDANDO_IMAGEM: "Falta validar a imagem",
    A.VALIDADA: "Validada",
    A.CANCELADA: "Cancelada",
}


# ─── Status ──────────────────────────────────────────────────────────

def calcular_status(aula: A.Aula, cr: Optional[ClassReport], idr: Optional[ImageDirectorReport],
                    hoje: Optional[date] = None) -> str:
    """O status da aula a partir do que está ligado nela."""
    hoje = hoje or date.today()
    if cr is not None and cr.status == "CANCELADO":
        return A.CANCELADA
    if cr is None:
        if aula.cancelada_na_agenda:
            return A.CANCELADA
        return A.PREVISTA if aula.data >= hoje else A.SEM_RELATORIO
    if cr.status == "RASCUNHO":
        return A.DEVOLVIDA if cr.precisa_correcao else A.EM_RELATORIO
    if cr.status in ("AGUARDANDO_VALIDACAO", "FINALIZADO"):
        return A.AGUARDANDO_VALIDACAO
    if cr.status == "VALIDADO":
        if idr is not None and idr.status == "CANCELADO":
            return A.CANCELADA
        if idr is not None and idr.status != "VALIDADO":
            return A.AGUARDANDO_IMAGEM
        return A.VALIDADA
    return A.EM_RELATORIO


def _cobrar(cr, idr) -> Optional[str]:
    # sem o relatório do assistente a aula não foi registrada: não há o que cobrar ainda
    if cr is None:
        return None
    from app.services.audit_export import classificar_lancamento, cobrar_conforme_status

    try:
        _, regra = classificar_lancamento(cr, idr)
        return cobrar_conforme_status(cr, idr, regra)[:80]
    except Exception:  # noqa: BLE001 — o cálculo do faturamento nunca derruba a tela
        return None


# ─── Assinatura (para não recalcular dia que não mudou) ───────────────

def _assinatura_grade(db: Session) -> str:
    n = db.query(func.count(Grade.id)).scalar() or 0
    ativa = db.query(func.max(GradeVersao.data_ativacao)).scalar()
    n_ativas = db.query(func.count(GradeVersao.id)).filter(GradeVersao.is_active == True).scalar() or 0  # noqa: E712
    n_turmas = db.query(func.count(Turma.id)).filter(Turma.is_active == True).scalar() or 0  # noqa: E712
    return f"{n}:{ativa}:{n_ativas}:{n_turmas}"


def _assinaturas(db: Session, inicio: date, fim: date) -> Dict[date, str]:
    """Uma assinatura por dia do período, com poucas consultas para o período todo."""
    por_dia: Dict[date, list] = defaultdict(list)
    grade = _assinatura_grade(db)
    hoje = date.today()

    for r in db.query(
        ClassReport.id, ClassReport.data_aula, ClassReport.status, ClassReport.precisa_correcao,
        ClassReport.video_link, ClassReport.slide_link, ClassReport.turma_id, ClassReport.disciplina_id,
        ClassReport.start_time, ClassReport.horario_aula, ClassReport.is_deleted, ClassReport.estudio,
    ).filter(ClassReport.data_aula >= inicio, ClassReport.data_aula <= fim).all():
        por_dia[r.data_aula].append(("cr", str(r.id), r.status, r.precisa_correcao, bool(r.video_link),
                                     bool(r.slide_link), str(r.turma_id), str(r.disciplina_id),
                                     str(r.start_time), r.horario_aula, r.is_deleted, r.estudio))
    for r in db.query(
        ImageDirectorReport.id, ImageDirectorReport.data_relatorio, ImageDirectorReport.status,
        ImageDirectorReport.turno, ImageDirectorReport.estudio, ImageDirectorReport.is_deleted,
        ImageDirectorReport.class_report_id,
    ).filter(ImageDirectorReport.data_relatorio >= inicio, ImageDirectorReport.data_relatorio <= fim).all():
        por_dia[r.data_relatorio].append(("idr", str(r.id), r.status, r.turno, r.estudio, r.is_deleted,
                                          str(r.class_report_id)))
    for r in db.query(
        ImageDirectorReport.data_relatorio, ImageDirectorLesson.id, ImageDirectorLesson.class_report_id,
    ).join(ImageDirectorLesson, ImageDirectorLesson.report_id == ImageDirectorReport.id).filter(
        ImageDirectorReport.data_relatorio >= inicio, ImageDirectorReport.data_relatorio <= fim
    ).all():
        por_dia[r.data_relatorio].append(("lesson", str(r.id), str(r.class_report_id)))
    for r in db.query(
        AgendamentoEstudio.data, func.count(AgendamentoEstudio.id), func.max(AgendamentoEstudio.atualizado_em),
    ).filter(AgendamentoEstudio.data >= inicio, AgendamentoEstudio.data <= fim).group_by(AgendamentoEstudio.data).all():
        por_dia[r[0]].append(("agenda", r[1], str(r[2])))
    for r in db.query(FeriadoAgenda.data, FeriadoAgenda.nome).filter(
        FeriadoAgenda.data >= inicio, FeriadoAgenda.data <= fim
    ).all():
        por_dia[r.data].append(("feriado", r.nome))

    saida = {}
    d = inicio
    while d <= fim:
        partes = sorted(repr(x) for x in por_dia.get(d, []))
        base = f"v1|{grade}|{d < hoje}|" + "|".join(partes)
        saida[d] = hashlib.sha256(base.encode()).hexdigest()
        d += timedelta(days=1)
    return saida


# ─── Sincronização ───────────────────────────────────────────────────

def sincronizar_periodo(db: Session, inicio: date, fim: date, forcar: bool = False) -> int:
    """Recalcula os dias do período cuja assinatura mudou. Devolve quantos dias recalculou."""
    if fim < inicio:
        inicio, fim = fim, inicio
    assinaturas = _assinaturas(db, inicio, fim)
    feitas = {
        s.data: s for s in db.query(A.AulaSincronizacao).filter(
            A.AulaSincronizacao.data >= inicio, A.AulaSincronizacao.data <= fim
        ).all()
    }
    recalculados = 0
    for dia, assinatura in assinaturas.items():
        s = feitas.get(dia)
        if not forcar and s and s.assinatura == assinatura:
            continue
        sincronizar_dia(db, dia)
        if s is None:
            s = A.AulaSincronizacao(data=dia, assinatura=assinatura)
            db.add(s)
        s.assinatura = assinatura
        s.sincronizado_em = datetime.now(timezone.utc)
        recalculados += 1
    db.commit()
    return recalculados


def _faixa(inicio, fim) -> Optional[str]:
    if inicio and fim:
        return f"{inicio.strftime('%H:%M')} às {fim.strftime('%H:%M')}"
    return None


def sincronizar_dia(db: Session, dia: date) -> List[A.Aula]:
    """Recalcula as aulas de um dia (não faz commit)."""
    with db.no_autoflush:
        return _sincronizar_dia(db, dia)


def _sincronizar_dia(db: Session, dia: date) -> List[A.Aula]:
    from app.services.agenda_conferencia import casar_relatorios, chave_estudio, chave_turno
    from app.services.agenda_estudios import TIPOS_DE_AULA, aulas_do_dia, turno_do_horario

    hoje = date.today()
    existentes = db.query(A.Aula).filter(A.Aula.data == dia).all()
    # Ligações anteriores (aula → relatório). Zeradas aqui e refeitas abaixo:
    # evita que o mesmo relatório fique em duas aulas no meio do recálculo.
    antes = {a.id: a.class_report_id for a in existentes}
    for a in existentes:
        a.class_report_id = None
    if existentes:
        db.flush()
    por_grade = {a.grade_id: a for a in existentes if a.grade_id}
    por_agend = {a.agendamento_id: a for a in existentes if a.agendamento_id}
    vivas: set = set()
    feriado = db.query(FeriadoAgenda).filter(FeriadoAgenda.data == dia).first()

    # 1. Grade vigente do dia (com cancelamentos e remanejamentos da Agenda)
    slots = []
    for s in aulas_do_dia(db, dia):
        if s.get("tipo_slot") not in (None, "aula", "gravacao"):
            continue
        gid = UUID(s["grade_id"])
        a = por_grade.get(gid)
        if a is None:
            a = A.Aula(id=uuid.uuid4(), data=dia, grade_id=gid, origem=A.ORIGEM_GRADE)
            db.add(a)
            por_grade[gid] = a
        a.turma_id = UUID(s["turma_id"]) if s.get("turma_id") else None
        a.disciplina_id = UUID(s["disciplina_id"]) if s.get("disciplina_id") else None
        a.professor_id = UUID(s["professor_id"]) if s.get("professor_id") else None
        a.estudio_id = s.get("estudio_efetivo") or s.get("estudio_id")
        a.inicio, a.fim = s.get("inicio"), s.get("fim")
        a.horario_texto = s.get("ordinal") or _faixa(a.inicio, a.fim)
        a.tipo = "gravacao" if s.get("tipo_slot") == "gravacao" else "aula"
        a.remanejada = bool(s.get("remanejada"))
        oc = s.get("ocorrencia")
        a.cancelada_na_agenda = bool(s.get("cancelada")) or bool(feriado)
        a.motivo_cancelamento = (f"Feriado: {feriado.nome}" if feriado else
                                 (oc.descricao if (oc is not None and s.get("cancelada")) else None))
        a.fora_da_grade = False
        vivas.add(a.id)
        s2 = dict(s)
        s2["aula"] = a
        slots.append(s2)

    # 2. Gravações e aulas extras marcadas na Agenda para uma turma
    for ag in db.query(AgendamentoEstudio).filter(
        AgendamentoEstudio.data == dia,
        AgendamentoEstudio.status == "AGENDADO",
        AgendamentoEstudio.tipo.in_(TIPOS_DE_AULA),
        AgendamentoEstudio.turma_id.isnot(None),
    ).all():
        a = por_agend.get(ag.id)
        if a is None:
            a = A.Aula(id=uuid.uuid4(), data=dia, agendamento_id=ag.id, origem=A.ORIGEM_AGENDA)
            db.add(a)
            por_agend[ag.id] = a
        a.turma_id = ag.turma_id
        a.estudio_id = ag.estudio_id
        a.inicio, a.fim = ag.horario_inicio, ag.horario_fim
        a.horario_texto = _faixa(a.inicio, a.fim)
        a.tipo = "aula_extra" if ag.tipo == "AULA_EXTRA" else "gravacao"
        a.cancelada_na_agenda = False
        a.motivo_cancelamento = None
        # gravação ligada a uma aula da grade: herda disciplina/professor dela
        gref = ag.grade_exibicao_id or ag.grade_id
        if gref:
            g = db.get(Grade, gref)
            if g:
                a.disciplina_id, a.professor_id = g.disciplina_id, g.professor_id
        vivas.add(a.id)
        slots.append({
            "grade_id": f"ag:{ag.id}", "turma_id": str(ag.turma_id),
            "disciplina_id": str(a.disciplina_id) if a.disciplina_id else None,
            "inicio": a.inicio, "fim": a.fim, "ordinal": None, "gravacao_sem_horario": False,
            "aula": a,
        })

    # 3. Relatórios de aula do dia
    crs = db.query(ClassReport).filter(ClassReport.data_aula == dia, ClassReport.is_deleted == False).all()  # noqa: E712
    por_id = {cr.id: cr for cr in crs}
    ligado: Dict[UUID, A.Aula] = {}
    # mantém ligações que continuam válidas
    for s in slots:
        a = s["aula"]
        cid = antes.get(a.id)
        if cid and cid in por_id and cid not in ligado:
            a.class_report_id = cid
            ligado[cid] = a
    livres_slots = [s for s in slots if s["aula"].class_report_id is None]
    for passo in ("ativos", "cancelados"):
        candidatos = [cr for cr in crs if cr.id not in ligado and
                      ((cr.status != "CANCELADO") if passo == "ativos" else (cr.status == "CANCELADO"))]
        casados, _ = casar_relatorios(livres_slots, candidatos)
        for s in list(livres_slots):
            cr = casados.get(s["grade_id"])
            if cr:
                s["aula"].class_report_id = cr.id
                ligado[cr.id] = s["aula"]
                livres_slots.remove(s)

    # aula que saiu da grade mas já tinha relatório: fica, marcada
    # (antes de criar aulas próprias, para o relatório continuar na mesma aula)
    for a in existentes:
        if a.id in vivas:
            continue
        cid = antes.get(a.id)
        if cid and cid in por_id and cid not in ligado:
            a.class_report_id = cid
            a.fora_da_grade = a.origem != A.ORIGEM_RELATORIO
            ligado[cid] = a
            vivas.add(a.id)

    # relatório sem aula prevista: vira aula própria (nada fica fora da conferência)
    estudios = {chave_estudio(e.nome): e.id for e in db.query(Estudio).all()}
    soltos_existentes = {antes[a.id]: a for a in existentes
                         if a.origem == A.ORIGEM_RELATORIO and antes.get(a.id)}
    for cr in crs:
        if cr.id in ligado:
            continue
        a = soltos_existentes.get(cr.id)
        if a is None:
            a = A.Aula(id=uuid.uuid4(), data=dia, origem=A.ORIGEM_RELATORIO)
            db.add(a)
        a.class_report_id = cr.id
        a.turma_id, a.disciplina_id, a.professor_id = cr.turma_id, cr.disciplina_id, cr.professor_id
        a.estudio_id = estudios.get(chave_estudio(cr.estudio))
        a.inicio, a.fim = cr.start_time, cr.end_time
        a.horario_texto = cr.horario_aula
        a.tipo = "aula"
        a.cancelada_na_agenda = False
        ligado[cr.id] = a
        vivas.add(a.id)

    # o que sobrou sem relatório e saiu da grade/agenda é apagado
    for a in existentes:
        if a.id not in vivas:
            db.delete(a)

    # 4. Relatório do diretor de imagem
    idrs = db.query(ImageDirectorReport).filter(
        ImageDirectorReport.data_relatorio == dia, ImageDirectorReport.is_deleted == False  # noqa: E712
    ).all()
    licoes = {}
    if idrs:
        for l in db.query(ImageDirectorLesson).filter(
            ImageDirectorLesson.report_id.in_([i.id for i in idrs])
        ).all():
            if l.class_report_id:
                licoes[l.class_report_id] = l
    idr_por_id = {i.id: i for i in idrs}
    nome_estudio = {e.id: e.nome for e in db.query(Estudio).all()}
    por_turno: Dict[tuple, ImageDirectorReport] = {}
    for i in sorted(idrs, key=lambda x: (x.status == "CANCELADO", str(x.id))):
        por_turno.setdefault((chave_turno(i.turno), chave_estudio(i.estudio)), i)

    db.flush()
    for a in [x for x in db.query(A.Aula).filter(A.Aula.data == dia).all() if x.id in vivas]:
        cr = por_id.get(a.class_report_id) if a.class_report_id else None
        idr = None
        a.image_director_lesson_id = None
        if cr is not None:
            lic = licoes.get(cr.id)
            if lic is not None:
                a.image_director_lesson_id = lic.id
                idr = idr_por_id.get(lic.report_id)
            if idr is None:
                ligados = [i for i in idrs if i.class_report_id == cr.id]
                idr = ligados[0] if ligados else None
        if idr is None and a.inicio is not None and a.estudio_id:
            idr = por_turno.get((turno_do_horario(a.inicio), chave_estudio(nome_estudio.get(a.estudio_id))))
        a.image_director_report_id = idr.id if idr else None

        a.status = calcular_status(a, cr, idr, hoje)
        a.tem_video = bool(cr and cr.video_link)
        a.tem_pdf = bool(cr and cr.slide_link)
        a.cobrar = _cobrar(cr, idr)
    db.flush()
    return [a for a in db.query(A.Aula).filter(A.Aula.data == dia).all()]


# ─── Leitura para as telas ───────────────────────────────────────────

def _nomes(db: Session, modelo, ids: Iterable) -> Dict:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    return {x.id: x for x in db.query(modelo).filter(modelo.id.in_(ids)).all()}


def para_dicts(db: Session, aulas: List[A.Aula]) -> List[dict]:
    turmas = _nomes(db, Turma, (a.turma_id for a in aulas))
    discs = _nomes(db, Disciplina, (a.disciplina_id for a in aulas))
    profs = _nomes(db, Professor, (a.professor_id for a in aulas))
    ests = _nomes(db, Estudio, (a.estudio_id for a in aulas))
    crs = _nomes(db, ClassReport, (a.class_report_id for a in aulas))
    idrs = _nomes(db, ImageDirectorReport, (a.image_director_report_id for a in aulas))
    saida = []
    for a in aulas:
        t, d, p, e = turmas.get(a.turma_id), discs.get(a.disciplina_id), profs.get(a.professor_id), ests.get(a.estudio_id)
        cr, idr = crs.get(a.class_report_id), idrs.get(a.image_director_report_id)
        saida.append({
            "id": str(a.id),
            "data": a.data.isoformat(),
            "inicio": a.inicio.strftime("%H:%M") if a.inicio else None,
            "fim": a.fim.strftime("%H:%M") if a.fim else None,
            "horario": a.horario_texto,
            "turma_id": str(a.turma_id) if a.turma_id else None,
            "turma": (t.nomenclatura_padrao or t.nome) if t else None,
            "modalidade": t.modalidade if t else None,
            "disciplina_id": str(a.disciplina_id) if a.disciplina_id else None,
            "disciplina": d.nome if d else None,
            "professor_id": str(a.professor_id) if a.professor_id else None,
            "professor": p.nome if p else None,
            "estudio_id": a.estudio_id,
            "estudio": e.nome if e else None,
            "tipo": a.tipo,
            "origem": a.origem,
            "remanejada": a.remanejada,
            "fora_da_grade": a.fora_da_grade,
            "motivo_cancelamento": a.motivo_cancelamento,
            "status": a.status,
            "status_rotulo": STATUS_ROTULO.get(a.status, a.status),
            "tem_video": a.tem_video,
            "tem_pdf": a.tem_pdf,
            "cobrar": a.cobrar,
            "class_report_id": str(a.class_report_id) if a.class_report_id else None,
            "class_report_autor": str(cr.created_by) if cr else None,
            "precisa_correcao": bool(cr and cr.precisa_correcao),
            "observacao_coordenacao": cr.observacao_coordenacao if cr else None,
            "image_director_report_id": str(a.image_director_report_id) if a.image_director_report_id else None,
            "imagem_status": idr.status if idr else None,
        })
    return saida


def listar(db: Session, inicio: date, fim: date, *, turma_id=None, estudio_id=None, status=None,
           busca: Optional[str] = None, autor_id=None, sincronizar: bool = True) -> List[A.Aula]:
    if (fim - inicio).days > MAX_DIAS:
        fim = inicio + timedelta(days=MAX_DIAS)
    if sincronizar:
        sincronizar_periodo(db, inicio, fim)
    q = db.query(A.Aula).filter(A.Aula.data >= inicio, A.Aula.data <= fim)
    if turma_id:
        q = q.filter(A.Aula.turma_id == turma_id)
    if estudio_id:
        q = q.filter(A.Aula.estudio_id == estudio_id)
    if status:
        lista = [s for s in str(status).split(",") if s in A.STATUS_AULA]
        if lista:
            q = q.filter(A.Aula.status.in_(lista))
    if autor_id:
        q = q.join(ClassReport, ClassReport.id == A.Aula.class_report_id).filter(ClassReport.created_by == autor_id)
    aulas = q.order_by(A.Aula.data, A.Aula.inicio.nullslast(), A.Aula.estudio_id).all()
    if busca:
        termo = busca.strip().lower()
        dicts = {d["id"]: d for d in para_dicts(db, aulas)}
        aulas = [a for a in aulas if termo in " ".join(
            str(dicts[str(a.id)].get(k) or "") for k in ("turma", "disciplina", "professor", "estudio")
        ).lower()]
    return aulas


def resumo(aulas: List[A.Aula]) -> Dict[str, int]:
    contagem = {s: 0 for s in A.STATUS_AULA}
    for a in aulas:
        contagem[a.status] = contagem.get(a.status, 0) + 1
    contagem["total"] = len(aulas)
    return contagem


def agora(db: Session, momento: Optional[datetime] = None) -> List[dict]:
    """Por estúdio: a aula no ar agora e a próxima (modo Agora / tela da TV)."""
    from app.services.agenda_estudios import estudios_ativos

    momento = momento or datetime.now()
    hoje = momento.date()
    sincronizar_periodo(db, hoje, hoje)
    aulas = para_dicts(db, db.query(A.Aula).filter(A.Aula.data == hoje).order_by(A.Aula.inicio.nullslast()).all())
    hm = momento.strftime("%H:%M")
    saida = []
    for e in estudios_ativos(db):
        do_estudio = [x for x in aulas if x["estudio_id"] == e.id and x["inicio"] and x["status"] != A.CANCELADA]
        no_ar = next((x for x in do_estudio if x["inicio"] <= hm < (x["fim"] or "99:99")), None)
        proxima = next((x for x in do_estudio if x["inicio"] > hm), None)
        saida.append({"estudio_id": e.id, "estudio": e.nome, "no_ar": no_ar, "proxima": proxima,
                      "restantes_hoje": len([x for x in do_estudio if x["inicio"] > hm])})
    return saida
