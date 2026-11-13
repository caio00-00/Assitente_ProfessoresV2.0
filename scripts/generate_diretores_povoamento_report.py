"""
Gera relatório e CSV de povoamento de diretores de imagem (HML).

Uso:
  python scripts/generate_diretores_povoamento_report.py
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "data/import/idr_agosto_2026_payload.json"
CSV_CADASTRO = ROOT / "data/diretores_imagem.csv"
OUT_CSV = ROOT / "data/import/diretores_imagem_povoamento.csv"
OUT_MD = ROOT / "data/import/relatorio_povoamento_diretores_imagem.md"
EMAIL_DOMAIN = "hml.oroshub.local"

# Nomes inválidos capturados pelo parser
INVALID_NAMES = {
    "HORÁRIO DE ENTRADA/SAÍDA:",
    "HORARIO DE ENTRADA/SAIDA:",
}


@dataclass
class DirectorEntry:
    nome_txt: str
    nome_cadastro: str
    email: str
    relatorios_agosto: int
    match_tipo: str
    user_id: str
    diretor_id: str


def norm_key(text: str) -> str:
    if not text:
        return ""
    n = unicodedata.normalize("NFKD", text)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^A-Z0-9 ]", " ", n.upper())
    return re.sub(r"\s+", " ", n).strip()


def slug_email(name: str) -> str:
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-zA-Z0-9]+", ".", n.lower()).strip(".")
    return re.sub(r"\.+", ".", n)


def load_cadastro() -> List[str]:
    names = []
    if not CSV_CADASTRO.exists():
        return names
    for line in CSV_CADASTRO.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip().rstrip(";").strip().lstrip("\ufeff")
        if line:
            names.append(line.upper())
    return names


def match_cadastro(txt_name: str, cadastro: List[str]) -> Tuple[str, str]:
    key = norm_key(txt_name)
    if not key or key in {norm_key(x) for x in INVALID_NAMES}:
        return txt_name, "invalido"

    for full in cadastro:
        if norm_key(full) == key:
            return full, "exato"

    # primeiro token
    first = key.split()[0] if key.split() else ""
    candidates = [c for c in cadastro if first and first in norm_key(c).split()]
    if len(candidates) == 1:
        return candidates[0], "primeiro_nome"

    # substring
    subs = [c for c in cadastro if key in norm_key(c) or norm_key(c) in key]
    if len(subs) == 1:
        return subs[0], "parcial"

    # heurísticas conhecidas
    aliases = {
        "PABLLO LOBO": "PABLLO ROOSVELLT DOS SANTOS LOBO",
        "GILBERTO ROCHA": "GILBERTO RODRIGUES DA ROCHA",
        "GILBERTO RODRIGUES": "GILBERTO RODRIGUES DA ROCHA",
        "MAYOLLY": "MAYOLLY SENA DA ROCHA",
        "MAYOLLY SENA": "MAYOLLY SENA DA ROCHA",
        "DANIEL FONSECA": "DANIEL FONSECA DA SILVA NASCIMENTO",
        "DANIEL DA SILVA": "DANIEL FONSECA DA SILVA NASCIMENTO",
        "THIAGO SOUSA": "THIAGO DA CONCEICAO SOUSA",
        "JACKSON DANIEL": "JACKSON ONORIO DANIEL",
        "NILTOMAR ANDRADE": "ANTONIO NILTOMAR DE ANDRADE",
        "ECILMAR": "ECILMAR MONTEIRO DE BRITO SILVA",
        "ESTENIO PAZ": "ESTENIO OLIVEIRA PAZ",
        "FLAVILTON MOURAO": "FLAVILTON DA SILVA MOURAO",
        "JUNIOR FEITOSA": "JOSÉ RIBAMAR FEITOSA DO NASCIMENTO JUNIOR",
        "SANTYAGO": "ADAYLTON SANTIAGO PORTELA E SILVA",
        "FELIPE CARVALHO": "FELIPE CARVALHO COSTA",
        "FELIPE CARVALHO COSTA": "FELIPE CARVALHO COSTA",
        "RENAN MESQUITA": "RENAN MESQUITA DE MELO SILVA",
        "MARIANA BARBOSA": "MARIANA BARBOSA DE SOUSA",
        "OCIONEIDE DE SOUSA": "OCIONEIDE DE SOUSA",
        "ANDERSON VITOR": "ANDERSON VITOR DOS SANTOS",
        "ANTONIO JR": "ANTONIO GONCALVES FERREIRA JUNIOR",
        "ISAEL MELO": "ISAEL DAVID DA SILVA MELO",
        "JAILSON": "JAILSON BARBOSA DA CUNHA",
        "JAILSON BARBOSA": "JAILSON BARBOSA DA CUNHA",
        "PAULO CESAR": "PAULO CESAR",  # pode não estar no CSV
        "FABRICIO BATISTA": "FABRICIO BATISTA",
        "BRUNO": "BRUNO",
        "KHALIL": "KHALIL SAREV LOPES VERA CRUZ",
    }
    if key in aliases:
        alias = aliases[key]
        for full in cadastro:
            if norm_key(full) == norm_key(alias):
                return full, "alias"
        return alias.upper(), "alias_sem_csv"

    return txt_name.upper(), "nao_mapeado"


def build_entries() -> List[DirectorEntry]:
    cadastro = load_cadastro()
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    counts = Counter()
    txt_by_canonical: Dict[str, set] = defaultdict(set)

    for rec in payload.get("records", []):
        raw = (rec.get("diretor") or "").strip().upper()
        if not raw or raw in INVALID_NAMES:
            continue
        canonical, _ = match_cadastro(raw, cadastro)
        key = norm_key(canonical)
        counts[key] += 1
        txt_by_canonical[key].add(raw)

    used_emails: set = set()
    entries: List[DirectorEntry] = []

    for key, qtd in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        sample_txt = sorted(txt_by_canonical[key])[0]
        canonical, match_tipo = match_cadastro(sample_txt, cadastro)

        base = slug_email(canonical)
        email = f"{base}@{EMAIL_DOMAIN}"
        suffix = 2
        while email in used_emails:
            email = f"{base}{suffix}@{EMAIL_DOMAIN}"
            suffix += 1
        used_emails.add(email)

        entries.append(
            DirectorEntry(
                nome_txt=sample_txt,
                nome_cadastro=canonical,
                email=email,
                relatorios_agosto=qtd,
                match_tipo=match_tipo,
                user_id=str(uuid.uuid4()),
                diretor_id=str(uuid.uuid4()),
            )
        )

    return entries


def write_csv(entries: List[DirectorEntry]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(
            [
                "nome_cadastro",
                "nome_no_txt",
                "email_ficticio",
                "role",
                "senha_inicial",
                "relatorios_agosto",
                "match_tipo",
                "diretor_imagem_id",
                "user_id",
            ]
        )
        for e in entries:
            w.writerow(
                [
                    e.nome_cadastro,
                    e.nome_txt,
                    e.email,
                    "diretor_imagem",
                    "Trocar@123",
                    e.relatorios_agosto,
                    e.match_tipo,
                    e.diretor_id,
                    e.user_id,
                ]
            )


def write_report(entries: List[DirectorEntry]) -> None:
    total_rel = sum(e.relatorios_agosto for e in entries)
    by_match = Counter(e.match_tipo for e in entries)
    nao_mapeados = [e for e in entries if e.match_tipo in ("nao_mapeado", "alias_sem_csv", "invalido")]

    lines = [
        "# Relatório de povoamento — Diretores de Imagem (HML)",
        "",
        "Gerado a partir do payload `idr_agosto_2026_payload.json` e cadastro `data/diretores_imagem.csv`.",
        "",
        "## Resumo",
        "",
        f"| Métrica | Valor |",
        f"|---------|------:|",
        f"| Diretores distintos (agosto) | **{len(entries)}** |",
        f"| Relatórios IDR referenciados | **{total_rel}** |",
        f"| E-mails fictícios gerados | **{len(entries)}** |",
        f"| Domínio | `{EMAIL_DOMAIN}` |",
        "",
        "## Tipos de correspondência nome TXT → cadastro",
        "",
    ]
    for tipo, qtd in sorted(by_match.items(), key=lambda x: -x[1]):
        lines.append(f"- **{tipo}**: {qtd}")

    lines.extend(
        [
            "",
            "## Tabela de povoamento",
            "",
            "| Nome cadastro | Nome no TXT | E-mail fictício | Rel. ago | Match |",
            "|---------------|-------------|-----------------|--------:|-------|",
        ]
    )
    for e in entries:
        lines.append(
            f"| {e.nome_cadastro} | {e.nome_txt} | `{e.email}` | {e.relatorios_agosto} | {e.match_tipo} |"
        )

    if nao_mapeados:
        lines.extend(["", "## Atenção — revisar manualmente", ""])
        for e in nao_mapeados:
            lines.append(f"- **{e.nome_txt}** → `{e.nome_cadastro}` ({e.match_tipo})")

    lines.extend(
        [
            "",
            "## Arquivos gerados",
            "",
            f"- CSV: `{OUT_CSV.relative_to(ROOT).as_posix()}`",
            f"- Este relatório: `{OUT_MD.relative_to(ROOT).as_posix()}`",
            "",
            "## Próximo passo (Dokploy)",
            "",
            "Após revisar este relatório:",
            "",
            "```bash",
            "cd /app",
            "python scripts/seed_diretores_imagem_hml.py --dry-run",
            "python scripts/seed_diretores_imagem_hml.py --apply",
            "python scripts/import_idr_agosto_hml.py --apply",
            "```",
            "",
            "**Nota:** e-mails são fictícios (`@hml.oroshub.local`), senha inicial sugerida `Trocar@123`.",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    entries = build_entries()
    write_csv(entries)
    write_report(entries)
    print(f"Diretores: {len(entries)}")
    print(f"CSV: {OUT_CSV}")
    print(f"Report: {OUT_MD}")


if __name__ == "__main__":
    main()
