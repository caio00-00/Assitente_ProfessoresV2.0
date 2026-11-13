"""Resolução de horários de slot por tipo de turma (espelha HORARIO_MAP do frontend)."""

import re
from datetime import datetime, time
from typing import List, Optional, Tuple

HORARIO_MAP = {
    ("TI", "1º Horário"): ("07:30", "08:30"),
    ("TI", "2º Horário"): ("08:30", "09:30"),
    ("TI", "3º Horário"): ("09:50", "10:50"),
    ("TI", "4º Horário"): ("10:50", "11:50"),
    ("TI", "5º Horário"): ("12:50", "13:50"),
    ("TI", "6º Horário"): ("13:50", "14:50"),
    ("TI", "7º Horário"): ("15:10", "16:10"),
    ("TI", "8º Horário"): ("16:10", "17:10"),
    ("MANHA", "1º Horário"): ("07:00", "08:00"),
    ("MANHA", "2º Horário"): ("08:00", "09:00"),
    ("MANHA", "3º Horário"): ("09:00", "10:00"),
    ("MANHA", "4º Horário"): ("10:20", "11:20"),
    ("MANHA", "5º Horário"): ("11:20", "12:20"),
    ("TARDE", "1º Horário"): ("13:00", "14:00"),
    ("TARDE", "2º Horário"): ("14:00", "15:00"),
    ("TARDE", "3º Horário"): ("15:00", "16:00"),
    ("TARDE", "4º Horário"): ("16:20", "17:20"),
    ("TARDE", "5º Horário"): ("17:20", "18:20"),
    ("NOITE_EM", "1º Horário"): ("18:30", "19:15"),
    ("NOITE_EM", "2º Horário"): ("19:15", "20:00"),
    ("NOITE_EM", "3º Horário"): ("20:00", "20:45"),
    ("NOITE_EM", "4º Horário"): ("20:45", "21:30"),
    ("NOITE_EM", "5º Horário"): ("21:30", "22:15"),
    ("EJA", "1º Horário"): ("18:00", "19:00"),
    ("EJA", "2º Horário"): ("19:00", "20:00"),
    ("EJA", "3º Horário"): ("20:00", "21:00"),
    ("EJA", "4º Horário"): ("21:00", "22:00"),
}


def ordinal_horario(horario_aula: Optional[str]) -> Optional[int]:
    """'3º Horário' -> 3. Retorna None quando não é um horário ordinal."""
    if not horario_aula:
        return None
    m = re.match(r"^\s*(\d{1,2})\s*[ºo°ª]?\s*hor", str(horario_aula), re.IGNORECASE)
    return int(m.group(1)) if m else None


def ordinal_label(n: int) -> str:
    return f"{n}º Horário"


def format_faixa(start: Optional[time], end: Optional[time]) -> Optional[str]:
    """'HH:MM às HH:MM' (ou None quando faltam horários)."""
    if not start or not end:
        return None
    return f"{start.strftime('%H:%M')} às {end.strftime('%H:%M')}"


def get_tipo_horario(
    turno: str = "",
    nomenclatura_turma: str = "",
    modalidade: str = "",
) -> str:
    """
    Tipo da tabela de horários considerando turno + modalidade da turma.

    - Integral (TI) tem numeração contínua manhã → tarde;
    - EJA / EJATEC (inclusive modalidade TECNICO noturna) usa a tabela EJA;
    - REGULAR / TECNICO / UAPI usam a tabela do turno (Manhã, Tarde, Noite).
    """
    mod = (modalidade or "").upper()
    if "EJA" in mod:
        return "EJA"
    return get_tipo_por_turno(turno, nomenclatura_turma or mod)


def horarios_padrao(tipo: str) -> List[Tuple[str, str, str]]:
    """Lista ordenada [(ordinal, início, fim)] da tabela padrão do tipo."""
    itens = [(k[1], v[0], v[1]) for k, v in HORARIO_MAP.items() if k[0] == tipo]
    return sorted(itens, key=lambda x: ordinal_horario(x[0]) or 0)


def is_ti_nomenclatura(nomenclatura: str) -> bool:
    """'EM 1 TI' → True; 'EM 1 TIM' (manhã) → False."""
    return bool(re.search(r"(^|[\s\-])TI($|[\s\-])", (nomenclatura or "").upper()))


def get_tipo_turma(nomenclatura: str) -> str:
    n = (nomenclatura or "").upper()
    if "EJA" in n:
        return "EJA"
    if is_ti_nomenclatura(n):
        return "TI"
    if "MANHA" in n or "MANHÃ" in n:
        return "MANHA"
    if "TARDE" in n:
        return "TARDE"
    if "NOITE" in n:
        return "NOITE_EM"
    return "NOITE_EM"


def get_tipo_por_turno(turno: str, nomenclatura_turma: str) -> str:
    t = (turno or "").upper()
    n = (nomenclatura_turma or "").upper()
    if "INTEGRAL" in t or is_ti_nomenclatura(n):
        return "TI"
    if "MANHÃ" in t or "MANHA" in t:
        return "MANHA"
    if "TARDE" in t:
        return "TARDE"
    if "NOITE" in t:
        if "EJA" in n:
            return "EJA"
        return "NOITE_EM"
    return get_tipo_turma(nomenclatura_turma)


def resolver_horario(
    horario_aula: str,
    nomenclatura_turma: str,
    turno_usuario: str = "",
) -> Tuple[Optional[time], Optional[time]]:
    """Retorna (start_time, end_time) a partir do horário da aula."""
    if not horario_aula:
        return (None, None)

    if "às" in horario_aula:
        try:
            parts = horario_aula.split("às")
            h1 = parts[0].strip()
            h2 = parts[1].strip()
            if len(h1) == 5:
                h1 += ":00"
            if len(h2) == 5:
                h2 += ":00"
            return (
                datetime.strptime(h1, "%H:%M:%S").time(),
                datetime.strptime(h2, "%H:%M:%S").time(),
            )
        except Exception:
            pass

    if turno_usuario:
        tipo = get_tipo_por_turno(turno_usuario, nomenclatura_turma)
    else:
        tipo = get_tipo_turma(nomenclatura_turma)

    intervalo = HORARIO_MAP.get((tipo, horario_aula))
    if intervalo:
        return (
            datetime.strptime(intervalo[0] + ":00", "%H:%M:%S").time(),
            datetime.strptime(intervalo[1] + ":00", "%H:%M:%S").time(),
        )
    return (None, None)
