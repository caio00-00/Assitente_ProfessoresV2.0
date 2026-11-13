"""
Parser de relatórios do Diretor de Imagem em formato .txt (export Drive).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class ParsedLesson:
    numero_aula: int
    disciplina: str
    professor: str
    transmissao_ou_gravada: str = "Transmissão"
    video_corrompido: str = "Não"
    video_corrompido_obs: Optional[str] = None
    interrupcoes: str = "Não"
    problema_audio: str = "Não"
    problema_audio_obs: Optional[str] = None
    vinhetas_corretas: str = "Sim"
    vinhetas_corretas_obs: Optional[str] = None
    creditos_corretos: str = "Sim"
    observacoes: Optional[str] = None
    canal_utilizado: Optional[str] = None
    horario_aula: Optional[str] = None


@dataclass
class ParsedDirectorReport:
    source_file: str
    serie: Optional[str] = None
    turno: Optional[str] = None
    data_relatorio: Optional[date] = None
    diretor: Optional[str] = None
    horario_entrada: Optional[str] = None
    horario_saida: Optional[str] = None
    estudio: Optional[str] = None
    youtube_link: Optional[str] = None
    canal_iptv: Optional[str] = None
    observacoes_gerais: Optional[str] = None
    lessons: List[ParsedLesson] = field(default_factory=list)
    parse_errors: List[str] = field(default_factory=list)


def _strip_accents(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def norm_key(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = _strip_accents(str(text)).upper()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def norm_turno(text: Optional[str]) -> str:
    key = norm_key(text)
    if "MANHA" in key or key == "MANHÃ":
        return "Manhã"
    if "TARDE" in key:
        return "Tarde"
    if "NOITE" in key:
        return "Noite"
    if key == "OUTRO":
        return "Outro"
    return text.strip() if text else ""


def infer_turno_from_text(text: Optional[str]) -> Optional[str]:
    key = norm_key(text)
    if not key:
        return None
    if "MANHA" in key:
        return "Manhã"
    if "TARDE" in key:
        return "Tarde"
    if "NOITE" in key:
        return "Noite"
    return None


def normalize_observacoes(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value.strip())
    if not text:
        return None
    compact = text.replace(" ", "")
    if compact and set(compact) <= {"=", "-", "*"}:
        return None
    text = re.sub(r"\s*=+\s*$", "", text).strip()
    if not text:
        return None
    compact = text.replace(" ", "")
    if compact and set(compact) <= {"=", "-", "*"}:
        return None
    return text


def _parse_labeled_line(block: str, label: str) -> Optional[str]:
    m = re.search(rf"{re.escape(label)}:[ \t]*([^\r\n]*)", block, flags=re.IGNORECASE)
    if not m:
        return None
    val = m.group(1).strip()
    if val and not val.upper().startswith("DETALHAMENTO"):
        return val
    m2 = re.search(
        rf"{re.escape(label)}:[ \t]*\r?\n[ \t]*([^\r\n]+)",
        block,
        flags=re.IGNORECASE,
    )
    if m2:
        val2 = m2.group(1).strip()
        if val2 and not val2.upper().startswith("DETALHAMENTO") and not val2.startswith("-"):
            return val2
    return None


def sanitize_professor_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    text = name.strip()
    key = norm_key(text)
    if not key or key.startswith("DETALHAMENTO") or key in {"DISCIPLINA", "OBS"}:
        return None
    return text


def norm_estudio(text: Optional[str]) -> str:
    if not text:
        return ""
    raw = norm_key(text)
    m = re.search(r"(\d+)", raw)
    if m:
        num = int(m.group(1))
        return f"ESTÚDIO {num}"
    return text.strip()


def parse_date_value(raw: str) -> Optional[date]:
    raw = (raw or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_yes_no(block: str, label: str, default: str = "Não") -> str:
    pattern = rf"{re.escape(label)}\s*\??\s*\n?\s*([^\n]+)"
    m = re.search(pattern, block, flags=re.IGNORECASE)
    if not m:
        return default
    val = norm_key(m.group(1))
    if val.startswith("SIM") or "AO VIVO" in val or "TRANSMISS" in val or "GRAVAD" in val:
        if "TRANSMISS" in val or "AO VIVO" in val:
            return "Sim" if "NAO" not in val and "NÃO" not in m.group(1).upper() else default
        return "Sim"
    if val.startswith("NAO") or val == "N":
        return "Não"
    return default


def _parse_transmissao(block: str) -> str:
    m = re.search(
        r"FOI TRANSMISS[AÃ]O OU AULA GRAVADA\?\s*\n?\s*([^\n]+)",
        block,
        flags=re.IGNORECASE,
    )
    if not m:
        return "Transmissão"
    val = norm_key(m.group(1))
    if "GRAVAD" in val and "TRANSMISS" not in val and "AO VIVO" not in val:
        return "Aula gravada"
    if "GRAVAD" in val and ("TRANSMISS" in val or "AO VIVO" in val):
        return "Transmissão"
    if "GRAVAD" in val:
        return "Aula gravada"
    return "Transmissão"


def _parse_obs(block: str) -> Optional[str]:
    m = re.search(r"OBS:\s*(.+?)(?:={3,}|$)", block, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    obs = re.sub(r"\s+", " ", m.group(1)).strip()
    return obs or None


def normalize_canal(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = value.strip()
    if not text or set(text) <= {"=", "-", " "}:
        return None
    if len(text) > 50:
        text = text[:50]
    return text


def _extract_header(text: str, report: ParsedDirectorReport) -> None:
    patterns = {
        "serie": r"S[ÉE]RIE:\s*(.+)",
        "turno": r"TURNO:\s*(.+)",
        "data": r"DATA:\s*(\d{2}/\d{2}/\d{2,4})",
        "diretor": r"DIRETOR:\s*(.+)",
        "estudio": r"EST[UÚ]DIO(?:\s*:\s*|\s+)(\d+|[\w\s]+)",
        "youtube": r"(?:LINK DO YOUTUBE|LINK):\s*(https?://\S+)",
        "canal": r"CANAL(?:\s+IPTV)?:[ \t]*([^\r\n]*)",
        "horarios": r"HOR[ÁA]RIO DE ENTRADA/SA[ÍI]DA:\s*([0-9:]{4,5})\s*/\s*([0-9:]{4,5})",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, flags=re.IGNORECASE)
        if not m:
            continue
        if key == "serie":
            report.serie = m.group(1).strip()
        elif key == "turno":
            report.turno = norm_turno(m.group(1))
        elif key == "data":
            report.data_relatorio = parse_date_value(m.group(1))
        elif key == "diretor":
            report.diretor = m.group(1).strip()
        elif key == "estudio":
            report.estudio = norm_estudio(m.group(1))
        elif key == "youtube":
            report.youtube_link = m.group(1).strip()
        elif key == "canal":
            report.canal_iptv = normalize_canal(m.group(1))
        elif key == "horarios":
            report.horario_entrada = m.group(1).strip()
            report.horario_saida = m.group(2).strip()

    if not report.estudio:
        m = re.search(r"EST[UÚ]DIO\s*(\d+)", text, flags=re.IGNORECASE)
        if m:
            report.estudio = norm_estudio(m.group(1))

    if not report.youtube_link:
        m = re.search(r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be)\S+)", text, flags=re.IGNORECASE)
        if m:
            report.youtube_link = m.group(1).strip()

    if not report.turno or report.turno not in {"Manhã", "Tarde", "Noite", "Outro"}:
        for hint in (report.serie, report.source_file, text):
            inferred = infer_turno_from_text(hint)
            if inferred:
                report.turno = inferred
                break


def _split_lesson_blocks(text: str) -> List[tuple[int, str]]:
    blocks: List[tuple[int, str]] = []
    for m in re.finditer(
        r"AULA\s*0*(\d+)\s*\n(.*?)(?=AULA\s*0*\d+\s*\n|={3,}\s*$|={3,}\s*\nOBS:|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        blocks.append((int(m.group(1)), m.group(0)))
    return blocks


def parse_idr_txt(content: str, source_file: str = "") -> ParsedDirectorReport:
    report = ParsedDirectorReport(source_file=source_file)
    _extract_header(content, report)

    for numero, block in _split_lesson_blocks(content):
        disciplina = _parse_labeled_line(block, "DISCIPLINA")
        professor = _parse_labeled_line(block, "PROFESSOR")
        if not disciplina or not professor:
            report.parse_errors.append(f"AULA {numero:02d} sem disciplina/professor")
            continue

        lesson = ParsedLesson(
            numero_aula=numero,
            disciplina=disciplina,
            professor=professor,
            transmissao_ou_gravada=_parse_transmissao(block),
            video_corrompido=_parse_yes_no(block, "VÍDEO CORROMPIDO", "Não"),
            interrupcoes=_parse_yes_no(
                block, "INTERRUPÇÕES ANTES OU DURANTE A AULA", "Não"
            ),
            problema_audio=_parse_yes_no(block, "HOUVE PROBLEMA DE ÁUDIO", "Não"),
            vinhetas_corretas=_parse_yes_no(
                block, "FORAM COLOCADAS AS VINHETAS CORRETAMENTE", "Sim"
            ),
            creditos_corretos=_parse_yes_no(
                block, "FORAM COLOCADOS OS CRÉDITOS CORRETOS", "Sim"
            ),
            observacoes=_parse_obs(block),
            canal_utilizado=report.canal_iptv,
        )
        report.lessons.append(lesson)

    obs_global = re.search(r"={3,}\s*\nOBS:\s*(.+)$", content, flags=re.IGNORECASE | re.DOTALL)
    if obs_global:
        report.observacoes_gerais = normalize_observacoes(
            re.sub(r"\s+", " ", obs_global.group(1)).strip()
        )

    if not report.data_relatorio:
        report.parse_errors.append("DATA não encontrada")
    if not report.lessons:
        report.parse_errors.append("Nenhuma AULA parseada")
    return report


def parse_idr_txt_file(path: Path) -> ParsedDirectorReport:
    content = path.read_text(encoding="utf-8", errors="ignore")
    return parse_idr_txt(content, source_file=path.name)
