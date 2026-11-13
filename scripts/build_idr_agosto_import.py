"""
Gera payload JSON para importação de relatórios IDR (agosto/2026).

Uso local (antes do deploy):
  python scripts/build_idr_agosto_import.py \
    --txt-dir "C:/Users/.../drive-download-..." \
    --excel "C:/Users/.../relatorios_audit_2026-09-07 (1).xlsx" \
    --month 2026-08

Saída:
  data/import/idr_agosto_2026_payload.json
  data/import/idr_agosto_2026_match_report.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from openpyxl import load_workbook

from app.services.idr_txt_parser import (
    norm_estudio,
    norm_key,
    norm_turno,
    parse_idr_txt_file,
)
from app.services.image_director_associacao import _norm_youtube


def _parse_excel_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    parts = text.split("/")
    if len(parts) != 3:
        return None
    d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
    return date(y, m, d)


def load_assistente_rows(excel_path: Path, month_prefix: str) -> List[Dict[str, Any]]:
    wb = load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb["Assistente"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    headers = rows[0]
    idx = {name: i for i, name in enumerate(headers)}
    yt_col = idx.get("YOUTUBE LINK")
    if yt_col is None:
        yt_col = next((i for i, n in enumerate(headers) if n and "YOUTUBE" in str(n).upper()), None)

    out = []
    for row in rows[1:]:
        data = _parse_excel_date(row[idx["DATA"]])
        if not data or not data.isoformat().startswith(month_prefix):
            continue
        out.append(
            {
                "class_report_id": str(row[idx["ID"]]) if row[idx["ID"]] else None,
                "data_aula": data.isoformat(),
                "turno": norm_turno(row[idx["TURNO"]]),
                "estudio": norm_estudio(row[idx["ESTÚDIO"]]),
                "curso": row[idx["CURSO"]],
                "horario": row[idx["HORÁRIO"]],
                "disciplina": row[idx["DISCIPLINA"]],
                "professor": row[idx["PROFESSOR"]],
                "youtube": row[yt_col] if yt_col is not None else None,
                "diretor_imagem": row[idx["DIRETOR IMAGEM"]] if "DIRETOR IMAGEM" in idx else None,
            }
        )
    return out


def _lesson_match_score(lesson: Dict, row: Dict) -> int:
    score = 0
    if lesson["data_relatorio"] == row["data_aula"]:
        score += 4
    if lesson["turno"] == row["turno"]:
        score += 3
    if lesson["estudio"] == row["estudio"]:
        score += 3
    if norm_key(lesson["disciplina"]) == norm_key(row["disciplina"]):
        score += 5
    if norm_key(lesson["professor"]) == norm_key(row["professor"]):
        score += 4
    yt_l = _norm_youtube(lesson.get("youtube_link"))
    yt_r = _norm_youtube(row.get("youtube"))
    if yt_l and yt_r and yt_l == yt_r:
        score += 6
    return score


def match_lesson_to_assistente(
    lesson: Dict[str, Any],
    assistente_rows: List[Dict[str, Any]],
    used_ids: set,
) -> Tuple[Optional[str], int, str]:
    best_id = None
    best_score = 0
    for row in assistente_rows:
        cid = row["class_report_id"]
        if not cid or cid in used_ids:
            continue
        score = _lesson_match_score(lesson, row)
        if score > best_score:
            best_score = score
            best_id = cid
    if best_score >= 15:
        return best_id, best_score, "slot+youtube" if best_score >= 21 else "slot"
    if best_score >= 12:
        return best_id, best_score, "slot_parcial"
    return None, best_score, "sem_match"


def build_payload(txt_dir: Path, excel_path: Path, month_prefix: str) -> Tuple[Dict, Dict]:
    assistente = load_assistente_rows(excel_path, month_prefix)
    used_class_ids: set = set()
    records = []
    stats = Counter()
    unmatched_examples = []

    for txt_path in sorted(txt_dir.glob("*.txt")):
        parsed = parse_idr_txt_file(txt_path)
        if not parsed.data_relatorio or not parsed.data_relatorio.isoformat().startswith(month_prefix):
            continue
        if parsed.parse_errors and not parsed.lessons:
            stats["txt_parse_fail"] += 1
            continue
        stats["txt_aug"] += 1

        # Agrupa aulas por disciplina (modelo v3.3: 1 IDR por disciplina/slot)
        groups: Dict[str, List] = defaultdict(list)
        for lesson in parsed.lessons:
            groups[norm_key(lesson.disciplina)].append(lesson)

        for _disc_key, lessons in groups.items():
            lessons.sort(key=lambda x: x.numero_aula)
            primary = lessons[0]
            payload_lesson = {
                "data_relatorio": parsed.data_relatorio.isoformat(),
                "turno": parsed.turno or "",
                "estudio": parsed.estudio or "",
                "serie": parsed.serie,
                "diretor": parsed.diretor,
                "youtube_link": parsed.youtube_link,
                "horario_entrada": parsed.horario_entrada,
                "horario_saida": parsed.horario_saida,
                "canal_iptv": parsed.canal_iptv,
                "observacoes_gerais": parsed.observacoes_gerais,
                "disciplina": primary.disciplina,
                "professor": primary.professor,
                "source_file": parsed.source_file,
                "lessons": [
                    {
                        "numero_aula": ls.numero_aula,
                        "disciplina_nome": ls.disciplina,
                        "professor_nome": ls.professor,
                        "transmissao_ou_gravada": ls.transmissao_ou_gravada,
                        "video_corrompido": ls.video_corrompido,
                        "interrupcoes": ls.interrupcoes,
                        "problema_audio": ls.problema_audio,
                        "vinhetas_corretas": ls.vinhetas_corretas,
                        "creditos_corretos": ls.creditos_corretos,
                        "observacoes": ls.observacoes,
                        "canal_utilizado": ls.canal_utilizado,
                    }
                    for ls in lessons
                ],
            }

            match = {
                "data_relatorio": payload_lesson["data_relatorio"],
                "turno": payload_lesson["turno"],
                "estudio": payload_lesson["estudio"],
                "disciplina": payload_lesson["disciplina"],
                "professor": payload_lesson["professor"],
                "youtube_link": payload_lesson["youtube_link"],
            }
            class_id, score, reason = match_lesson_to_assistente(match, assistente, used_class_ids)
            payload_lesson["class_report_id"] = class_id
            payload_lesson["match_score"] = score
            payload_lesson["match_reason"] = reason
            if class_id:
                used_class_ids.add(class_id)
                stats["matched"] += 1
            else:
                stats["unmatched"] += 1
                if len(unmatched_examples) < 30:
                    unmatched_examples.append(
                        f"{parsed.source_file} | {payload_lesson['data_relatorio']} "
                        f"{payload_lesson['turno']} {payload_lesson['estudio']} "
                        f"{payload_lesson['disciplina']} / {payload_lesson['professor']} (score={score})"
                    )
            records.append(payload_lesson)
            stats["idr_records"] += 1

    payload = {
        "version": 1,
        "month": month_prefix,
        "source_excel": excel_path.name,
        "source_txt_dir": txt_dir.name,
        "generated_records": len(records),
        "records": records,
    }
    meta = {
        "stats": dict(stats),
        "assistente_rows": len(assistente),
        "unmatched_examples": unmatched_examples,
    }
    return payload, meta


def write_report(meta: Dict, out_path: Path) -> None:
    lines = [
        "# Relatório de correspondência IDR — agosto/2026",
        "",
        f"- Linhas Assistente (Excel): **{meta['assistente_rows']}**",
        f"- TXT agosto parseados: **{meta['stats'].get('txt_aug', 0)}**",
        f"- Registros IDR gerados: **{meta['stats'].get('idr_records', 0)}**",
        f"- Com match assistente: **{meta['stats'].get('matched', 0)}**",
        f"- Sem match: **{meta['stats'].get('unmatched', 0)}**",
        "",
        "## Exemplos sem match",
        "",
    ]
    for ex in meta["unmatched_examples"]:
        lines.append(f"- {ex}")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera payload de importação IDR")
    parser.add_argument("--txt-dir", required=True, help="Pasta com .txt do Drive")
    parser.add_argument("--excel", required=True, help="Excel exportado do audit")
    parser.add_argument("--month", default="2026-08", help="Prefixo YYYY-MM")
    parser.add_argument(
        "--out-json",
        default="data/import/idr_agosto_2026_payload.json",
        help="Arquivo JSON de saída",
    )
    parser.add_argument(
        "--out-report",
        default="data/import/idr_agosto_2026_match_report.md",
        help="Relatório markdown",
    )
    args = parser.parse_args()

    txt_dir = Path(args.txt_dir)
    excel_path = Path(args.excel)
    if not txt_dir.is_dir():
        raise SystemExit(f"Pasta não encontrada: {txt_dir}")
    if not excel_path.is_file():
        raise SystemExit(f"Excel não encontrado: {excel_path}")

    payload, meta = build_payload(txt_dir, excel_path, args.month)
    out_json = Path(args.out_json)
    out_report = Path(args.out_report)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(meta, out_report)

    print(f"JSON: {out_json} ({len(payload['records'])} registros)")
    print(f"Report: {out_report}")
    print("Stats:", meta["stats"])


if __name__ == "__main__":
    main()
