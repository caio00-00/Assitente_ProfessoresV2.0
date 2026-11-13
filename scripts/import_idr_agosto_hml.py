"""
Importa relatórios do Diretor de Imagem a partir de payload JSON.

Uso no console Dokploy (HML):
  cd /app
  python scripts/import_idr_agosto_hml.py --dry-run
  python scripts/import_idr_agosto_hml.py --apply

Variáveis:
  PAYLOAD_PATH=data/import/idr_agosto_2026_payload.json (default)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.auxiliares import Disciplina, Professor
from app.models.class_report import ClassReport
from app.models.diretor_imagem import DiretorImagem
from app.models.image_director_report import ImageDirectorLesson, ImageDirectorReport
from app.models.turma import Turma
from app.models.user import User
from app.services.idr_txt_parser import (
    infer_turno_from_text,
    norm_key,
    norm_turno,
    norm_estudio,
    normalize_canal,
    normalize_observacoes,
    sanitize_professor_name,
)
from app.services.image_director_associacao import associar_class_report


def _clip(value: Optional[str], max_len: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


DIRETOR_ALIASES = {
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
    "ANDERSON VITOR": "ANDERSON VITOR DOS SANTOS",
    "ANTONIO JR": "ANTONIO GONCALVES FERREIRA JUNIOR",
    "ISAEL MELO": "ISAEL DAVID DA SILVA MELO",
    "JAILSON": "JAILSON BARBOSA DA CUNHA",
    "JAILSON BARBOSA": "JAILSON BARBOSA DA CUNHA",
    "KHALIL": "KHALIL SAREV LOPES VERA CRUZ",
}


def _resolve_turno(rec: Dict[str, Any], class_report: Optional[ClassReport] = None) -> Optional[str]:
    for source in (rec.get("turno"), class_report.turno if class_report else None):
        turno = norm_turno(source)
        if turno in {"Manhã", "Tarde", "Noite", "Outro"}:
            return turno
    for hint in (rec.get("serie"), rec.get("source_file")):
        inferred = infer_turno_from_text(hint)
        if inferred:
            return inferred
    return None


def _professor_externo(rec: Dict[str, Any], prof: Optional[Professor]) -> Optional[str]:
    if prof:
        return None
    name = sanitize_professor_name(rec.get("professor"))
    if name:
        return _clip(name, 255)
    for ls in rec.get("lessons") or []:
        name = sanitize_professor_name(ls.get("professor_nome"))
        if name:
            return _clip(name, 255)
    return "Não informado"


def _parse_time(value: Optional[str]) -> Optional[time]:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


def _resolve_diretor(db: Session, name: Optional[str]) -> Optional[DiretorImagem]:
    if not name:
        return None
    key = norm_key(name)
    alias = DIRETOR_ALIASES.get(key)
    if alias:
        key = norm_key(alias)

    directors = db.query(DiretorImagem).filter(DiretorImagem.is_active == True).all()  # noqa: E712
    for d in directors:
        if norm_key(d.nome) == key:
            return d

    first = key.split()[0] if key.split() else ""
    candidates = [d for d in directors if first and first in norm_key(d.nome).split()]
    if len(candidates) == 1:
        return candidates[0]

    subs = [d for d in directors if key in norm_key(d.nome) or norm_key(d.nome) in key]
    if len(subs) == 1:
        return subs[0]

    for d in directors:
        if first and first in norm_key(d.nome):
            return d
    return None


def _resolve_professor(db: Session, name: Optional[str]) -> Optional[Professor]:
    if not name:
        return None
    key = norm_key(name)
    for p in db.query(Professor).all():
        if norm_key(p.nome) == key:
            return p
    return None


def _resolve_disciplina(db: Session, name: Optional[str]) -> Optional[Disciplina]:
    if not name:
        return None
    key = norm_key(name)
    for d in db.query(Disciplina).all():
        if norm_key(d.nome) == key:
            return d
    return None


def _resolve_turma_by_curso(db: Session, serie: Optional[str], turno: str) -> Optional[Turma]:
    if not serie:
        return None
    key = norm_key(serie)
    candidates = db.query(Turma).filter(Turma.is_active == True).all()  # noqa: E712
    turno_key = norm_key(turno)
    best = None
    for t in candidates:
        names = [norm_key(t.nome), norm_key(t.nomenclatura_padrao or "")]
        if key in names or any(key in n or n in key for n in names if n):
            if turno_key and turno_key[:3] in norm_key(t.turno or ""):
                return t
            best = best or t
    return best


def _admin_user(db: Session) -> User:
    user = db.query(User).filter(User.role == "admin", User.email_confirmed == True).first()  # noqa: E712
    if not user:
        user = db.query(User).filter(User.role == "admin").first()
    if not user:
        raise RuntimeError("Nenhum usuário admin encontrado para created_by.")
    return user


def _existing_idr(
    db: Session, rec: Dict[str, Any], diretor_id: uuid.UUID, turno: str
) -> Optional[ImageDirectorReport]:
    q = db.query(ImageDirectorReport).filter(
        ImageDirectorReport.is_deleted == False,  # noqa: E712
        ImageDirectorReport.data_relatorio == date.fromisoformat(rec["data_relatorio"]),
        ImageDirectorReport.turno == turno,
        ImageDirectorReport.estudio == rec["estudio"],
        ImageDirectorReport.diretor_imagem_id == diretor_id,
        ImageDirectorReport.disciplina_nome == rec["disciplina"],
    )
    if rec.get("class_report_id"):
        found = q.filter(ImageDirectorReport.class_report_id == rec["class_report_id"]).first()
        if found:
            return found
    return q.first()


def import_record(db: Session, rec: Dict[str, Any], admin: User, dry_run: bool) -> str:
    diretor = _resolve_diretor(db, rec.get("diretor"))
    if not diretor:
        return "skip_sem_diretor"

    class_report = None
    if rec.get("class_report_id"):
        class_report = (
            db.query(ClassReport)
            .filter(ClassReport.id == rec["class_report_id"], ClassReport.is_deleted == False)  # noqa: E712
            .first()
        )

    turno = _resolve_turno(rec, class_report)
    if not turno:
        return "skip_sem_turno"

    if _existing_idr(db, rec, diretor.id, turno):
        return "skip_duplicado"

    prof = _resolve_professor(db, rec.get("professor"))
    disc = _resolve_disciplina(db, rec.get("disciplina"))
    turma = _resolve_turma_by_curso(db, rec.get("serie"), turno)
    professor_externo = _professor_externo(rec, prof)

    if dry_run:
        return "would_insert"

    report = ImageDirectorReport(
        id=uuid.uuid4(),
        created_by=admin.id,
        created_at=datetime.now(timezone.utc),
        status="VALIDADO",
        finalized_at=datetime.now(timezone.utc),
        diretor_imagem_id=diretor.id,
        data_relatorio=date.fromisoformat(rec["data_relatorio"]),
        turno=_clip(turno, 20),
        estudio=_clip(norm_estudio(rec.get("estudio")), 50),
        turma_id=turma.id if turma else (class_report.turma_id if class_report else None),
        serie_modulo_manual=_clip(rec.get("serie"), 255),
        disciplina_id=disc.id if disc else (class_report.disciplina_id if class_report else None),
        disciplina_nome=_clip(rec.get("disciplina"), 255),
        professor_id=prof.id if prof else (class_report.professor_id if class_report else None),
        professor_nome_externo=None if prof else professor_externo,
        horario_aula=class_report.horario_aula if class_report else None,
        start_time=class_report.start_time if class_report else None,
        end_time=class_report.end_time if class_report else None,
        horario_entrada=_parse_time(rec.get("horario_entrada")),
        horario_saida=_parse_time(rec.get("horario_saida")),
        youtube_link=_clip(rec.get("youtube_link") or (class_report.youtube_link if class_report else None), 1000),
        observacoes_gerais=normalize_observacoes(rec.get("observacoes_gerais")),
        origem="grade",
        class_report_id=class_report.id if class_report else None,
    )
    db.add(report)
    db.flush()

    for ls in rec.get("lessons") or []:
        canal = normalize_canal(ls.get("canal_utilizado") or rec.get("canal_iptv"))
        prof_nome = sanitize_professor_name(ls.get("professor_nome")) or professor_externo or "Não informado"
        lesson = ImageDirectorLesson(
            id=uuid.uuid4(),
            report_id=report.id,
            numero_aula=int(ls["numero_aula"]),
            class_report_id=class_report.id if class_report else None,
            disciplina_nome=_clip(ls.get("disciplina_nome") or rec["disciplina"], 255),
            professor_nome=_clip(prof_nome, 255),
            canal_utilizado=_clip(canal, 50),
            transmissao_ou_gravada=_clip(ls.get("transmissao_ou_gravada") or "Transmissão", 20),
            video_corrompido=_clip(ls.get("video_corrompido") or "Não", 10),
            interrupcoes=_clip(ls.get("interrupcoes") or "Não", 10),
            problema_audio=_clip(ls.get("problema_audio") or "Não", 10),
            vinhetas_corretas=_clip(ls.get("vinhetas_corretas") or "Sim", 10),
            creditos_corretos=_clip(ls.get("creditos_corretos") or "Sim", 10),
            observacoes=ls.get("observacoes"),
        )
        db.add(lesson)

    if class_report:
        associar_class_report(db, report, class_report.id)

    return "inserted"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persiste no banco")
    parser.add_argument("--dry-run", action="store_true", help="Somente simula")
    parser.add_argument(
        "--payload",
        default=os.environ.get("PAYLOAD_PATH", "data/import/idr_agosto_2026_payload.json"),
    )
    args = parser.parse_args()
    dry_run = not args.apply
    if args.dry_run:
        dry_run = True

    payload_path = Path(args.payload)
    if not payload_path.is_file():
        raise SystemExit(f"Payload não encontrado: {payload_path}")

    data = json.loads(payload_path.read_text(encoding="utf-8"))
    records = data.get("records") or []
    stats: Dict[str, int] = {}

    db = SessionLocal()
    try:
        admin = _admin_user(db)
        for rec in records:
            result = import_record(db, rec, admin, dry_run=dry_run)
            stats[result] = stats.get(result, 0) + 1
        if not dry_run:
            db.commit()
            print("Commit OK.")
        else:
            db.rollback()
            print("Dry-run (rollback).")
        print("Stats:", stats)
        print(f"Total records: {len(records)}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
