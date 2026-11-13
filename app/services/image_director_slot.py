"""
Helpers de slot da grade para relatórios do Diretor de Imagem.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.auxiliares import Grade
from app.models.infraestrutura import GradeVersao
from app.models.class_report import ClassReport
from app.models.image_director_report import ImageDirectorReport
from app.models.turma import Turma
from app.services.image_director_associacao import (
    _horarios_compativeis,
    _normalize_horario_digits,
)
from app.services.horario_resolver import (
    HORARIO_MAP,
    get_tipo_horario,
    horarios_padrao,
    ordinal_horario,
    ordinal_label,
    resolver_horario,
)
from app.services.idr_txt_parser import norm_key


def _is_gravacao_slot(grade: Grade) -> bool:
    if not grade.horario_inicio:
        return False
    return grade.horario_inicio.strftime("%H:%M") == "00:00"


def _slot_horario_label(grade: Grade) -> str:
    if _is_gravacao_slot(grade):
        return "GRAVAÇÃO"
    h_ini = grade.horario_inicio.strftime("%H:%M") if grade.horario_inicio else ""
    h_fim = grade.horario_fim.strftime("%H:%M") if grade.horario_fim else ""
    return f"{h_ini} às {h_fim}"


def _turno_sort_key(turno_aula: Optional[str]) -> int:
    key = norm_key(turno_aula or "")
    if "MANHA" in key:
        return 0
    if "TARDE" in key:
        return 1
    if "NOITE" in key:
        return 2
    return 3


def _is_ti_turma(turma: Turma) -> bool:
    """Tempo integral: numeração contínua manhã → tarde no mesmo dia."""
    turno_key = norm_key(turma.turno or "")
    if "INTEGRAL" in turno_key:
        return True
    label = (turma.nomenclatura_padrao or turma.nome or "").upper()
    # Evita confundir "TIM" (manhã) com sufixo " TI" (tempo integral).
    if label.endswith(" TI") or label.endswith("-TI"):
        return True
    padded = f" {label} "
    return " TI " in padded or " TI-" in label


def _turno_matches(turno_ref: str, turno_aula: Optional[str]) -> bool:
    ref = norm_key(turno_ref)
    ta = norm_key(turno_aula or "")
    if not ref:
        return True
    if "MANHA" in ref:
        return "MANHA" in ta
    if "TARDE" in ref:
        return "TARDE" in ta
    if "NOITE" in ref:
        return "NOITE" in ta
    return ref in ta or ta in ref


def _slot_turno_label(grade: Grade) -> str:
    """Turno do slot: turno_aula cadastrado ou inferido pelo horário de início."""
    key = norm_key(grade.turno_aula or "")
    if "MANHA" in key:
        return "MANHA"
    if "TARDE" in key:
        return "TARDE"
    if "NOITE" in key:
        return "NOITE"
    h = grade.horario_inicio
    if not h:
        return ""
    if h < time(12, 30):
        return "MANHA"
    if h < time(18, 0):
        return "TARDE"
    return "NOITE"


def _turno_ref_key(turno: Optional[str]) -> str:
    key = norm_key(turno or "")
    for t in ("MANHA", "TARDE", "NOITE"):
        if t in key:
            return t
    return ""


def _slots_vigentes(db: Session, turma_id: UUID, target_date: date) -> List[Grade]:
    """
    Slots vigentes da turma no dia da semana.

    Com Grade v2, versões antigas continuam na tabela `grades` — usar só a
    versão ATIVA evita contar slots duplicados (o que deslocava a numeração
    1º/2º/3º... e fazia o horário não casar com a grade).
    """
    weekday = target_date.weekday()
    q = db.query(Grade).filter(
        Grade.turma_id == turma_id,
        Grade.dia_semana == weekday,
        and_(
            or_(Grade.vigencia_inicio <= target_date, Grade.vigencia_inicio.is_(None)),
            or_(Grade.vigencia_fim >= target_date, Grade.vigencia_fim.is_(None)),
        ),
    )
    slots = q.all()

    ativa = (
        db.query(GradeVersao)
        .filter(GradeVersao.turma_id == turma_id, GradeVersao.is_active == True)  # noqa: E712
        .order_by(GradeVersao.data_ativacao.desc().nullslast())
        .first()
    )
    if ativa:
        da_versao = [g for g in slots if g.grade_versao_id == ativa.id]
        if da_versao:
            slots = da_versao
    else:
        legado = [g for g in slots if g.grade_versao_id is None]
        if legado:
            slots = legado

    slots = [g for g in slots if not _is_gravacao_slot(g) and (g.tipo_slot or "aula") == "aula"]

    # Remove duplicatas exatas de horário (mesmo início/fim)
    vistos = set()
    unicos = []
    for g in sorted(slots, key=lambda x: (x.horario_inicio or time(0, 0), str(x.id))):
        chave = (g.horario_inicio, g.horario_fim)
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(g)
    return unicos


def list_ordered_slots_for_day(
    db: Session,
    turma_id: UUID,
    target_date: date,
    report_turno: Optional[str] = None,
) -> List[Grade]:
    """
    Slots da grade para o dia, ordenados conforme modalidade da turma.

    - TI (tempo integral): numeração contínua do dia (manhã 1º–4º, tarde 5º–8º);
    - REGULAR / TECNICO / EJA / UAPI: numeração reinicia a cada turno.
    """
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        return []

    slots = _slots_vigentes(db, turma_id, target_date)

    if _is_ti_turma(turma):
        ordem_turno = {"MANHA": 0, "TARDE": 1, "NOITE": 2}
        return sorted(
            slots,
            key=lambda g: (ordem_turno.get(_slot_turno_label(g), 3), g.horario_inicio or time(0, 0)),
        )

    turno_ref = _turno_ref_key(report_turno or turma.turno or "")
    if turno_ref:
        slots = [g for g in slots if _slot_turno_label(g) == turno_ref]
    return sorted(slots, key=lambda g: g.horario_inicio or time(0, 0))


def _min(t: time) -> int:
    return t.hour * 60 + t.minute


def _tipo_do_slot(turma: Turma, grade: Grade) -> str:
    """Tabela de horários do slot: TI (contínua) ou a do turno do próprio slot."""
    if _is_ti_turma(turma):
        return "TI"
    turno = {"MANHA": "MANHÃ", "TARDE": "TARDE", "NOITE": "NOITE"}.get(_slot_turno_label(grade), turma.turno or "")
    return get_tipo_horario(turno, turma.nomenclatura_padrao or turma.nome or "", turma.modalidade or "")


def numerar_slots(turma: Turma, ordered: List[Grade]) -> List[Tuple[int, Grade]]:
    """
    Número oficial de cada slot ("3º Horário"), pela tabela de horários da
    modalidade (TI: 1º 07:30, 2º 08:30, 3º 09:50…). Assim um dia sem a 1ª ou
    a 2ª aula não desloca a numeração: a aula das 09:50 continua sendo o 3º
    horário. Slot com horário fora da tabela (grade com horários próprios)
    recebe o número seguinte ao anterior.
    """
    saida: List[Tuple[int, Grade]] = []
    usados: set = set()
    anterior = 0
    tabelas: dict = {}
    for g in ordered:
        n = None
        if g.horario_inicio:
            tipo = _tipo_do_slot(turma, g)
            if tipo not in tabelas:
                tabelas[tipo] = [
                    (ordinal_horario(o), _min(datetime.strptime(ini, "%H:%M").time()))
                    for o, ini, _fim in horarios_padrao(tipo)
                ]
            ini = _min(g.horario_inicio)
            # início igual ao da tabela oficial, sem voltar para trás na numeração
            candidatos = [num for num, m in tabelas[tipo] if num and ini == m and num > anterior and num not in usados]
            if candidatos:
                n = candidatos[0]
        if n is None:
            n = anterior + 1
            while n in usados:
                n += 1
        usados.add(n)
        anterior = n
        saida.append((n, g))
    return saida


def list_numbered_slots_for_day(
    db: Session,
    turma_id: UUID,
    target_date: date,
    report_turno: Optional[str] = None,
) -> List[Tuple[int, Grade]]:
    """[(número oficial da aula, slot)] do dia — TI contínuo; demais por turno."""
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        return []
    return numerar_slots(turma, list_ordered_slots_for_day(db, turma_id, target_date, report_turno))


def slot_do_ordinal(numerados: List[Tuple[int, Grade]], ordinal: Optional[int]) -> Optional[Grade]:
    return next((g for n, g in numerados if n == ordinal), None) if ordinal else None


def list_turno_slots_numerados(
    db: Session,
    turma_id: UUID,
    target_date: date,
    turno: Optional[str] = None,
) -> List[Tuple[int, Grade]]:
    """
    [(número da aula, slot)] apenas do turno pedido, com a numeração correta
    da modalidade: TI tarde começa no 5º; regular/técnico reiniciam no 1º.
    """
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        return []
    numerados = list_numbered_slots_for_day(db, turma_id, target_date, turno)
    turno_ref = _turno_ref_key(turno)
    if _is_ti_turma(turma) and turno_ref:
        numerados = [(n, g) for n, g in numerados if _slot_turno_label(g) == turno_ref]
    return numerados


def compute_numero_aula_slot(
    db: Session,
    turma_id: UUID,
    data_relatorio: date,
    horario_aula: Optional[str] = None,
    class_report_id: Optional[UUID] = None,
    report_turno: Optional[str] = None,
) -> int:
    numerados = list_numbered_slots_for_day(db, turma_id, data_relatorio, report_turno)
    if not numerados:
        return ordinal_horario(horario_aula) or 1

    if class_report_id:
        cr = (
            db.query(ClassReport)
            .filter(ClassReport.id == class_report_id, ClassReport.is_deleted == False)  # noqa: E712
            .first()
        )
        if cr:
            for n, grade in numerados:
                label = _slot_horario_label(grade)
                disc_ok = not grade.disciplina_id or grade.disciplina_id == cr.disciplina_id
                if disc_ok and _horarios_compativeis(label, cr):
                    return n

    ordinal = ordinal_horario(horario_aula)
    if ordinal and slot_do_ordinal(numerados, ordinal):
        return ordinal

    if horario_aula:
        target_digits = _normalize_horario_digits(horario_aula)
        for n, grade in numerados:
            label = _slot_horario_label(grade)
            if horario_aula.strip() == label:
                return n
            if target_digits and _normalize_horario_digits(label) == target_digits:
                return n

    return 1


def find_existing_report_by_slot(
    db: Session,
    diretor_id: UUID,
    data: date,
    turno: str,
    estudio: str,
    *,
    class_report_id: Optional[UUID] = None,
    turma_id: Optional[UUID] = None,
    horario_aula: Optional[str] = None,
    turno_variants: Optional[List[str]] = None,
) -> Optional[ImageDirectorReport]:
    """Localiza IDR existente por slot (class_report_id ou horário+turma)."""
    q = db.query(ImageDirectorReport).filter(
        ImageDirectorReport.diretor_imagem_id == diretor_id,
        ImageDirectorReport.data_relatorio == data,
        ImageDirectorReport.estudio == estudio,
        ImageDirectorReport.is_deleted == False,  # noqa: E712
    )
    if turno_variants:
        q = q.filter(ImageDirectorReport.turno.in_(turno_variants))
    elif turno:
        q = q.filter(ImageDirectorReport.turno == turno)

    if class_report_id:
        found = q.filter(ImageDirectorReport.class_report_id == class_report_id).first()
        if found:
            return found

    if turma_id and horario_aula:
        candidates = q.filter(ImageDirectorReport.turma_id == turma_id).all()
        target_digits = _normalize_horario_digits(horario_aula)
        for report in candidates:
            if report.horario_aula == horario_aula.strip():
                return report
            if target_digits and _normalize_horario_digits(report.horario_aula) == target_digits:
                return report

    return None


# ─── Horário exato (HH:MM) por turno/modalidade ────────────────────────────


def _cache_key(turma_id, target_date, turno) -> tuple:
    return (str(turma_id), target_date.isoformat() if target_date else "", norm_key(turno or ""))


def _cached_ordered_slots(
    db: Session,
    turma_id: UUID,
    target_date: date,
    turno: Optional[str],
    cache: Optional[dict] = None,
) -> List[Grade]:
    if cache is None:
        return list_ordered_slots_for_day(db, turma_id, target_date, turno)
    key = _cache_key(turma_id, target_date, turno)
    if key not in cache:
        cache[key] = list_ordered_slots_for_day(db, turma_id, target_date, turno)
    return cache[key]


def _cached_numbered_slots(
    db: Session,
    turma_id: UUID,
    target_date: date,
    turno: Optional[str],
    cache: Optional[dict] = None,
) -> List[Tuple[int, Grade]]:
    turma = _turma_cached(db, turma_id, cache)
    if not turma:
        return []
    key = ("numerados",) + _cache_key(turma_id, target_date, turno)
    if cache is not None and key in cache:
        return cache[key]
    numerados = numerar_slots(turma, _cached_ordered_slots(db, turma_id, target_date, turno, cache))
    if cache is not None:
        cache[key] = numerados
    return numerados


def _turma_cached(db: Session, turma_id: UUID, cache: Optional[dict] = None) -> Optional[Turma]:
    if not turma_id:
        return None
    key = ("turma", str(turma_id))
    if cache is not None and key in cache:
        return cache[key]
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if cache is not None:
        cache[key] = turma
    return turma


def resolve_slot_times(
    db: Session,
    *,
    turma_id: Optional[UUID],
    data: Optional[date],
    turno: Optional[str],
    horario_aula: Optional[str],
    cache: Optional[dict] = None,
) -> Tuple[Optional[time], Optional[time]]:
    """
    Resolve (início, fim) exatos do slot, na ordem:
      1. faixa explícita "HH:MM às HH:MM" no próprio horário;
      2. grade horária real da turma no dia (por turno; TI contínuo) —
         cobre qualquer modalidade (REGULAR, TECNICO, EJA, UAPI);
      3. tabela padrão por turno/modalidade (HORARIO_MAP).
    """
    if not horario_aula or _is_gravacao_label(horario_aula):
        return (None, None)

    if "às" in horario_aula:
        st, et = resolver_horario(horario_aula, "", "")
        if st and et:
            return (st, et)

    turma = _turma_cached(db, turma_id, cache) if turma_id else None
    ordinal = ordinal_horario(horario_aula)

    if turma and data and ordinal:
        g = slot_do_ordinal(_cached_numbered_slots(db, turma.id, data, turno, cache), ordinal)
        if g and g.horario_inicio and g.horario_fim:
            return (g.horario_inicio, g.horario_fim)

    nomenclatura = ""
    modalidade = ""
    turno_ref = turno or ""
    if turma:
        nomenclatura = turma.nomenclatura_padrao or turma.nome or ""
        modalidade = turma.modalidade or ""
        if not turno_ref:
            turno_ref = turma.turno or ""
    tipo = get_tipo_horario(turno_ref, nomenclatura, modalidade)
    if turma and _is_ti_turma(turma):
        tipo = "TI"
    intervalo = HORARIO_MAP.get((tipo, (horario_aula or "").strip()))
    if not intervalo and ordinal:
        intervalo = HORARIO_MAP.get((tipo, ordinal_label(ordinal)))
    if intervalo:
        return (
            datetime.strptime(intervalo[0], "%H:%M").time(),
            datetime.strptime(intervalo[1], "%H:%M").time(),
        )
    return (None, None)


def _is_gravacao_label(value: Optional[str]) -> bool:
    return norm_key(value or "") in ("GRAVACAO",)


def _padrao_do_turno(tipo: str, turno: Optional[str]) -> List[Tuple[str, str, str]]:
    """Tabela padrão do tipo; no TI, só os horários do turno pedido (tarde = 5º–8º)."""
    itens = horarios_padrao(tipo)
    turno_ref = _turno_ref_key(turno)
    if tipo == "TI" and turno_ref:
        def _t(ini: str) -> str:
            h = datetime.strptime(ini, "%H:%M").time()
            return "MANHA" if h < time(12, 30) else ("TARDE" if h < time(18, 0) else "NOITE")
        filtrados = [i for i in itens if _t(i[1]) == turno_ref]
        if filtrados:
            return filtrados
    return itens


def list_horario_options(
    db: Session,
    *,
    turma_id: Optional[UUID],
    data: Optional[date],
    turno: Optional[str],
) -> dict:
    """
    Opções de horário do turno com número da aula e HH:MM, conforme a
    modalidade da turma (TI contínuo; demais reiniciam por turno).
    Fonte: grade vigente da turma no dia; sem grade, tabela padrão do tipo.
    """
    turma = _turma_cached(db, turma_id) if turma_id else None
    nomenclatura = (turma.nomenclatura_padrao or turma.nome or "") if turma else ""
    modalidade = (turma.modalidade or "") if turma else ""
    turno_ref = turno or (turma.turno if turma else "") or ""
    tipo = get_tipo_horario(turno_ref, nomenclatura, modalidade)
    if turma and _is_ti_turma(turma):
        tipo = "TI"

    opcoes = []
    fonte = "padrao"
    if turma and data:
        numerados = list_turno_slots_numerados(db, turma.id, data, turno)
        if numerados:
            fonte = "grade"
            for n, g in numerados:
                opcoes.append(
                    {
                        "value": ordinal_label(n),
                        "numero": n,
                        "inicio": g.horario_inicio.strftime("%H:%M") if g.horario_inicio else None,
                        "fim": g.horario_fim.strftime("%H:%M") if g.horario_fim else None,
                        "disciplina_id": str(g.disciplina_id) if g.disciplina_id else None,
                        "disciplina_nome": g.disciplina.nome if g.disciplina else None,
                        "turno_aula": _slot_turno_label(g),
                    }
                )
    if not opcoes:
        for ordinal, ini, fim in _padrao_do_turno(tipo, turno_ref):
            opcoes.append(
                {
                    "value": ordinal,
                    "numero": ordinal_horario(ordinal),
                    "inicio": ini,
                    "fim": fim,
                    "disciplina_id": None,
                    "disciplina_nome": None,
                    "turno_aula": None,
                }
            )
    for o in opcoes:
        o["faixa"] = f"{o['inicio']} às {o['fim']}" if o["inicio"] and o["fim"] else None
    return {
        "tipo": tipo,
        "modalidade": modalidade or None,
        "fonte": fonte,
        "opcoes": opcoes,
    }


def resolve_slot_ordinal(
    db: Session,
    *,
    turma_id: Optional[UUID],
    data: Optional[date],
    turno: Optional[str],
    horario_aula: Optional[str],
    start_time: Optional[time] = None,
    cache: Optional[dict] = None,
) -> Optional[int]:
    """Número da aula (1º, 2º, 5º...) do slot, casando com a grade vigente."""
    ordinal = ordinal_horario(horario_aula)
    if ordinal:
        return ordinal
    if not turma_id or not data:
        return None
    numerados = _cached_numbered_slots(db, turma_id, data, turno, cache)
    target = _normalize_horario_digits(horario_aula) if horario_aula else ""
    for n, g in numerados:
        if start_time and g.horario_inicio == start_time:
            return n
        if target and _normalize_horario_digits(_slot_horario_label(g)) == target:
            return n
    return None


def report_pertence_grade(
    db: Session,
    report: ImageDirectorReport,
    cache: Optional[dict] = None,
) -> bool:
    """
    True quando o relatório corresponde a um slot da grade horária da turma
    (mesmo sem ClassReport vinculado — caso comum das aulas REGULARES, em que o
    relatório do assistente ainda não foi lançado/associado).
    """
    if (getattr(report, "origem", "grade") or "grade") != "grade":
        return False
    if report.class_report_id:
        return True
    if not report.turma_id or not report.data_relatorio:
        return False
    numerados = _cached_numbered_slots(db, report.turma_id, report.data_relatorio, report.turno, cache)
    if not numerados:
        return False
    ordered = [g for _n, g in numerados]
    ordinal = ordinal_horario(report.horario_aula)
    if ordinal and slot_do_ordinal(numerados, ordinal):
        return True
    if report.horario_aula:
        target = _normalize_horario_digits(report.horario_aula)
        for g in ordered:
            if target and _normalize_horario_digits(_slot_horario_label(g)) == target:
                return True
    if report.disciplina_id and any(g.disciplina_id == report.disciplina_id for g in ordered):
        return True
    return False
