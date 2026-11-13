"""
Uso de estúdio — reunião de 26/10/2026.

Uma fonte só para a planilha "Uso de Estúdio" e para a API de consulta do sistema de cobrança:

- Fonte: relatórios FINALIZADOS (assistente + diretor de imagem ligados). Rascunho e cancelado ficam de fora.
- Cada uso guarda o horário inteiro (início e fim) e o TEMPO REAL em minutos.
- Planilha Excel: o uso é quebrado em blocos de 1 hora a partir do início; o último bloco fica
  com o tempo que sobrou (07:30–10:15 = 07:30–08:30, 08:30–09:30, 09:30–10:15). Não arredonda.
- API: um registro por uso, com os minutos exatos (07:30–10:15 = 165 min).
- Tipo de uso: Aula, Gravação, Gravação antecipada, Reposição, Exibição de aula antecipada, Evento.
- Gravação antecipada sem SEDUC não é cobrada (cobra só a exibição); com SEDUC cobra as duas.
- O professor é pago na gravação: na exibição de aula gravada antes o professor fica vazio.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import Workbook
from sqlalchemy.orm import Session

STATUS_FINALIZADOS = ("FINALIZADO", "AGUARDANDO_VALIDACAO", "VALIDADO")
_HORA = re.compile(r"(\d{1,2}):(\d{2})")

TIPO_AULA = "Aula"
TIPO_GRAVACAO = "Gravação"
TIPO_ANTECIPADA = "Gravação antecipada"
TIPO_REPOSICAO = "Reposição"
TIPO_EXIBICAO = "Exibição de aula antecipada"
TIPO_EVENTO = "Evento"


def _horas_do_texto(texto: str) -> Tuple[Optional[str], Optional[str]]:
    achados = _HORA.findall(texto or "")
    if len(achados) >= 2:
        (h1, m1), (h2, m2) = achados[0], achados[1]
        return f"{int(h1):02d}:{m1}", f"{int(h2):02d}:{m2}"
    return None, None


def _minutos(inicio: Optional[str], fim: Optional[str]) -> Optional[int]:
    if not inicio or not fim:
        return None
    h1, m1 = map(int, inicio.split(":"))
    h2, m2 = map(int, fim.split(":"))
    total = (h2 * 60 + m2) - (h1 * 60 + m1)
    return total if total > 0 else None


def quebrar_em_horas(inicio: str, fim: str) -> List[Tuple[str, str, int]]:
    """07:30–10:15 → [(07:30, 08:30, 60), (08:30, 09:30, 60), (09:30, 10:15, 45)]."""
    total = _minutos(inicio, fim)
    if not total:
        return [(inicio, fim, 0)]
    base = datetime.strptime(inicio, "%H:%M")
    blocos = []
    feito = 0
    while feito < total:
        dur = min(60, total - feito)
        ini = base + timedelta(minutes=feito)
        fim_b = ini + timedelta(minutes=dur)
        blocos.append((ini.strftime("%H:%M"), fim_b.strftime("%H:%M"), dur))
        feito += dur
    return blocos


def fmt_minutos(minutos: Optional[int]) -> str:
    if minutos is None:
        return ""
    return f"{minutos // 60}h{minutos % 60:02d}"


def _tipo_de_uso(cr, idr) -> Tuple[str, bool]:
    """(tipo de uso, cobrar) a partir da regra de cobrança já usada no faturamento."""
    from app.services.audit_export import classificar_lancamento
    from app.services.image_director_associacao import (
        classificar_modalidade_class_report,
        classificar_modalidade_idr,
    )

    lanc, cobrar = classificar_lancamento(cr, idr)
    cobra = cobrar == "Sim"
    if lanc == "EXIBIÇÃO DE AULA ANTECIPADA":
        return TIPO_EXIBICAO, cobra
    if lanc == "GRAVAÇÃO ANTECIPADA":
        return TIPO_ANTECIPADA, cobra
    if lanc == "REPOSIÇÃO":
        return TIPO_REPOSICAO, cobra
    if idr is not None and (getattr(idr, "nome_evento", None) or "").strip():
        return TIPO_EVENTO, cobra
    modalidade = (classificar_modalidade_class_report(cr) if cr else "") or (
        classificar_modalidade_idr(idr) if idr else ""
    )
    if modalidade == "GRAVACAO":
        return TIPO_GRAVACAO, cobra
    return TIPO_AULA, cobra


def _finalizado(rel) -> bool:
    return rel is not None and (getattr(rel, "status", None) or "") in STATUS_FINALIZADOS


def montar_usos(db: Session, filters, *, is_coord: bool = False) -> List[Dict[str, Any]]:
    """Um registro por uso do estúdio (relatório finalizado), com o tempo real em minutos."""
    from app.services.audit_export import (
        _build_pairings,
        _class_horario_str,
        _idr_horario_str,
        _load_class_reports,
        _load_idr_reports,
        _load_lookup_maps,
        _professor_name_class,
        _professor_nome_from_report,
        _status_label,
    )

    class_reports = [r for r in _load_class_reports(db, filters) if _finalizado(r)]
    idr_reports = [r for r in _load_idr_reports(db, filters) if _finalizado(r)]
    turmas_map, discs_map, profs_map, dir_map = _load_lookup_maps(db, class_reports, idr_reports)
    pairings, _ = _build_pairings(class_reports, idr_reports)

    usos: List[Dict[str, Any]] = []
    for cr, idr in pairings:
        tipo, cobra = _tipo_de_uso(cr, idr)
        turma = turmas_map.get(cr.turma_id if cr else idr.turma_id)
        disc = discs_map.get(cr.disciplina_id if cr else idr.disciplina_id)
        if cr is not None:
            data_uso = getattr(cr, "data_execucao_real", None) or cr.data_aula
            inicio, fim = _horas_do_texto(_class_horario_str(cr, turma))
        else:
            data_uso = getattr(idr, "data_execucao_real", None) or idr.data_relatorio
            inicio, fim = _horas_do_texto(_idr_horario_str(idr))
        minutos = _minutos(inicio, fim)

        referencia = None
        if tipo == TIPO_REPOSICAO:
            referencia = getattr(cr, "data_referencia_aula", None) if cr else getattr(idr, "data_referencia", None)
        elif tipo == TIPO_ANTECIPADA:
            referencia = getattr(cr, "data_referencia_aula", None) if cr else getattr(idr, "data_referencia", None)
        elif tipo == TIPO_EXIBICAO:
            m = re.search(r"(\d{2})/(\d{2})/(\d{4})", (getattr(cr, "motivo_referencia", None) if cr else "")
                          or (getattr(idr, "motivo_referencia", None) if idr else "") or "")
            if m:
                referencia = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

        if tipo == TIPO_EXIBICAO:
            professor = ""  # o professor é pago na gravação
        else:
            professor = _professor_name_class(cr, profs_map) if cr else ""
            if not professor and idr is not None:
                professor = _professor_nome_from_report(idr) or ""
        paga_professor = bool(professor) and tipo != TIPO_EXIBICAO and tipo != TIPO_EVENTO

        solicitante = (getattr(cr, "solicitante_antecipacao", None) if cr else None) or (
            getattr(idr, "solicitante_antecipacao", None) if idr else None
        ) or ""
        chamado = (getattr(cr, "ticket_number", None) if cr else None) or (
            getattr(idr, "ticket_number", None) if idr else None
        ) or ""
        diretor = ""
        if idr is not None and idr.diretor_imagem_id in dir_map:
            diretor = dir_map[idr.diretor_imagem_id].nome
        elif cr is not None and cr.diretor_imagem_id in dir_map:
            diretor = dir_map[cr.diretor_imagem_id].nome

        usos.append({
            "class_report_id": str(cr.id) if cr else None,
            "image_director_report_id": str(idr.id) if idr else None,
            "data": data_uso,
            "mes_faturamento": data_uso.strftime("%m/%Y") if data_uso else "",
            "estudio": (cr.estudio if cr else idr.estudio) or "",
            "turno": (cr.turno if cr else idr.turno) or "",
            "inicio": inicio,
            "fim": fim,
            "minutos": minutos,
            "tipo_uso": tipo,
            "cobrar": cobra,
            "seduc": solicitante == "SEDUC",
            "chamado": chamado,
            "turma": turma.nome if turma else (idr.turma_nome if idr else ""),
            "disciplina": disc.nome if disc else ((idr.disciplina_nome or "") if idr else ""),
            "titulo": (getattr(idr, "nome_evento", None) if idr else None) or "",
            "professor": professor,
            "paga_professor": paga_professor,
            "referencia": referencia,
            "diretor_imagem": "" if is_coord else diretor,
            "status_assistente": _status_label(cr.status, cr.precisa_correcao) if cr else "",
            "status_diretor": "" if is_coord else (_status_label(idr.status, idr.precisa_correcao) if idr else ""),
            "link_video": (cr.video_link if cr else "") or "",
            "link_pdf": (cr.slide_link if cr else "") or "",
        })
    usos.sort(key=lambda u: (u["data"] or date.min, u["estudio"], u["inicio"] or ""))
    return usos


def _br(d: Optional[date]) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def build_uso_estudio_workbook(db: Session, filters, user_role: Optional[str] = None) -> bytes:
    """Planilha única "Uso de Estúdio": uma linha por hora de estúdio usada."""
    from app.services.audit_export import (
        FAT_HEADER_FILL,
        _autosize_columns,
        _write_header,
        _write_row,
    )

    is_coord = user_role in ("coordenador", "coordenadora")
    usos = montar_usos(db, filters, is_coord=is_coord)

    wb = Workbook()
    ws = wb.active
    ws.title = "Uso de Estúdio"
    headers = [
        "DATA", "MÊS DE FATURAMENTO", "ESTÚDIO", "INÍCIO", "FIM", "BLOCO", "TEMPO (MIN)",
        "TIPO DE USO", "COBRAR", "SEDUC", "CHAMADO", "TURMA", "DISCIPLINA", "TÍTULO",
        "PROFESSOR", "PAGA PROFESSOR", "REFERÊNCIA",
    ]
    if not is_coord:
        headers.append("DIRETOR DE IMAGEM")
    headers.append("STATUS ASSISTENTE")
    if not is_coord:
        headers.append("STATUS DIRETOR")
    headers += ["LINK VÍDEO", "LINK PDF"]
    _write_header(ws, headers, fill=FAT_HEADER_FILL)

    linha = 2
    for u in usos:
        if u["inicio"] and u["fim"] and u["minutos"]:
            blocos = quebrar_em_horas(u["inicio"], u["fim"])
        else:
            blocos = [(u["inicio"] or "", u["fim"] or "", u["minutos"] or 0)]
        for i, (ini, fim, dur) in enumerate(blocos, start=1):
            valores = [
                _br(u["data"]), u["mes_faturamento"], u["estudio"], ini, fim,
                f"{i} de {len(blocos)}" if len(blocos) > 1 else "", dur or "",
                u["tipo_uso"], "Sim" if u["cobrar"] else "Não", "Sim" if u["seduc"] else "Não",
                u["chamado"], u["turma"], u["disciplina"], u["titulo"],
                u["professor"], "Sim" if u["paga_professor"] else "Não", _br(u["referencia"]),
            ]
            if not is_coord:
                valores.append(u["diretor_imagem"])
            valores.append(u["status_assistente"])
            if not is_coord:
                valores.append(u["status_diretor"])
            valores += [u["link_video"], u["link_pdf"]]
            _write_row(ws, linha, valores)
            linha += 1
    ws.freeze_panes = "A2"
    _autosize_columns(ws, len(headers), max(linha - 2, 0))

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def uso_para_api(u: Dict[str, Any]) -> Dict[str, Any]:
    """Registro da API de cobrança: um por uso, com o tempo exato (sem quebrar em horas)."""
    return {
        "data": u["data"].isoformat() if u["data"] else None,
        "mes_faturamento": u["mes_faturamento"],
        "estudio": u["estudio"],
        "turno": u["turno"],
        "inicio": u["inicio"],
        "fim": u["fim"],
        "minutos_uso": u["minutos"],
        "tempo_uso": fmt_minutos(u["minutos"]),
        "tipo_uso": u["tipo_uso"],
        "cobrar": u["cobrar"],
        "minutos_cobrados": (u["minutos"] or 0) if u["cobrar"] else 0,
        "seduc": u["seduc"],
        "chamado": u["chamado"] or None,
        "turma": u["turma"] or None,
        "disciplina": u["disciplina"] or None,
        "titulo": u["titulo"] or None,
        "professor": u["professor"] or None,
        "paga_professor": u["paga_professor"],
        "referencia": u["referencia"].isoformat() if u["referencia"] else None,
        "status_assistente": u["status_assistente"] or None,
        "status_diretor": u["status_diretor"] or None,
        "class_report_id": u["class_report_id"],
        "image_director_report_id": u["image_director_report_id"],
    }
