"""
Canal Educação v4 — Registro do histórico de versões dos relatórios.

`registrar_versao` tira uma foto das colunas do relatório (e, no relatório do
diretor, das aulas dentro dele) e guarda em report_versions junto com o que
mudou desde a versão anterior. Deve ser chamado na mesma transação da mudança,
antes do commit: se a mudança falhar, a versão também não fica gravada.
"""

import decimal
import uuid
from datetime import date, datetime, time
from typing import Any, Dict, Optional

from sqlalchemy import func, inspect as sa_inspect
from sqlalchemy.orm import Session

from app.models.historico import ReportVersion

TIPO_AULA = "class_report"
TIPO_IMAGEM = "image_director_report"

# Campos que não interessam no histórico (mudam sozinhos ou são técnicos)
_IGNORAR = {"updated_at", "md5_checksum"}


def _json(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_json(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _json(x) for k, x in v.items()}
    return str(v)


def foto(obj) -> Dict[str, Any]:
    """Snapshot das colunas do objeto (sem relacionamentos)."""
    mapper = sa_inspect(obj).mapper
    dados = {}
    for col in mapper.column_attrs:
        if col.key in _IGNORAR:
            continue
        dados[col.key] = _json(getattr(obj, col.key, None))
    # Relatório do diretor: inclui as aulas (é nelas que ficam vídeo corrompido, chamado etc.)
    aulas = getattr(obj, "lessons", None) or getattr(obj, "aulas", None)
    if aulas is not None and isinstance(aulas, (list, tuple)):
        dados["_aulas"] = [foto(a) for a in aulas]
    return dados


def _diferencas(antes: Optional[Dict[str, Any]], depois: Dict[str, Any]) -> Dict[str, list]:
    if not antes:
        return {}
    mudou = {}
    for k in set(antes) | set(depois):
        if antes.get(k) != depois.get(k):
            mudou[k] = [antes.get(k), depois.get(k)]
    return mudou


def ultima_versao(db: Session, tipo: str, report_id) -> Optional[ReportVersion]:
    return (
        db.query(ReportVersion)
        .filter(ReportVersion.tipo == tipo, ReportVersion.report_id == report_id)
        .order_by(ReportVersion.versao.desc())
        .first()
    )


def registrar_versao(
    db: Session,
    tipo: str,
    relatorio,
    evento: str,
    usuario=None,
    status_anterior: Optional[str] = None,
    motivo: Optional[str] = None,
) -> ReportVersion:
    """Grava uma versão. Não faz commit (fica na transação de quem chamou)."""
    db.flush()
    anterior = ultima_versao(db, tipo, relatorio.id)
    numero = (
        db.query(func.coalesce(func.max(ReportVersion.versao), 0))
        .filter(ReportVersion.tipo == tipo, ReportVersion.report_id == relatorio.id)
        .scalar()
        or 0
    ) + 1
    atual = foto(relatorio)
    versao = ReportVersion(
        tipo=tipo,
        report_id=relatorio.id,
        versao=numero,
        evento=evento,
        status_anterior=status_anterior,
        status_novo=getattr(relatorio, "status", None),
        alteracoes=_diferencas(anterior.snapshot if anterior else None, atual) or None,
        snapshot=atual,
        motivo=motivo,
        alterado_por=getattr(usuario, "id", None),
    )
    db.add(versao)
    return versao


def listar_versoes(db: Session, tipo: str, report_id):
    return (
        db.query(ReportVersion)
        .filter(ReportVersion.tipo == tipo, ReportVersion.report_id == report_id)
        .order_by(ReportVersion.versao.asc())
        .all()
    )
