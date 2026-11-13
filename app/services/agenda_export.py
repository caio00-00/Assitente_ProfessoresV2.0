"""
Exporta a Agenda de Estúdios no mesmo formato da planilha antiga:
uma aba por dia, blocos Manhã / Tarde / Noite, estúdios nas colunas.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.services.agenda_estudios import montar_agenda_dia

_FINO = Side(style="thin", color="FF9CA3AF")
_BORDA = Border(left=_FINO, right=_FINO, top=_FINO, bottom=_FINO)
_CENTRO = Alignment(horizontal="center", vertical="center", wrap_text=True)
_CINZA = PatternFill("solid", fgColor="FFD9D9D9")
_TITULO = PatternFill("solid", fgColor="FF1E293B")
_TURNO = {
    "manha": PatternFill("solid", fgColor="FFDBEAFE"),
    "tarde": PatternFill("solid", fgColor="FFFEE2E2"),
    "noite": PatternFill("solid", fgColor="FFEDE9FE"),
}
_CANCELADO = PatternFill("solid", fgColor="FFFF0000")


def _clarear(hex_cor: str, fator: float = 0.72) -> str:
    h = hex_cor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (int(c + (255 - c) * fator) for c in (r, g, b))
    return f"FF{r:02X}{g:02X}{b:02X}"


def _texto_item(it: dict) -> str:
    partes = []
    if it["tipo"] != "AULA":
        partes.append(it["tipo_label"].upper())
    partes.append(it["titulo"])
    if it.get("professor"):
        partes.append(it["professor"])
    if it["tipo"] != "AULA" and it.get("turma"):
        partes.append(it["turma"])
    if it.get("departamento"):
        partes.append(it["departamento"])
    if it.get("canal") and (it["tipo"] != "AULA" or it.get("remanejada")):
        partes.append(it["canal"])
    if it.get("chamado"):
        partes.append(f"Chamado #{it['chamado']}")
    if it.get("fantasma"):
        partes.append(f"REMANEJADA → {it.get('remanejada_para')}")
    elif it.get("remanejada"):
        partes.append(f"(remanejada do {it.get('remanejada_de')})")
    if it.get("cancelada"):
        partes.append("CANCELADO")
    return "\n".join(p for p in partes if p)


def _aba_do_dia(ws, agenda: dict, user_role: Optional[str] = None) -> None:
    is_coord = user_role in ("coordenador", "coordenadora")
    turnos = agenda["turnos"]
    n_est = max((len(t["estudios"]) for t in turnos), default=0)
    ultima_col = n_est + 1

    ws.column_dimensions["A"].width = 14
    for c in range(2, ultima_col + 1):
        ws.column_dimensions[get_column_letter(c)].width = 24

    d = date.fromisoformat(agenda["data"])
    ws.cell(1, 1, "AGENDA DE ESTÚDIOS").font = Font(bold=True, size=14, color="FFFFFFFF")
    ws.cell(1, 1).fill = _TITULO
    ws.cell(1, 1).alignment = _CENTRO
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(ultima_col, 2))
    ws.cell(2, 1, f"{d.strftime('%d/%m/%Y')} — {agenda['dia_semana_label'].upper()}").font = Font(bold=True)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(ultima_col, 2))

    linha = 4
    for t in turnos:
        est = t["estudios"]
        if is_coord:
            ws.cell(linha, 1, t["label"].upper()).font = Font(bold=True)
            ws.cell(linha + 1, 1, "Horário")
            for i, col in enumerate(est, start=2):
                ws.cell(linha, i, "\n".join(col["turmas"]) or "—")
                ws.cell(linha + 1, i, col["estudio_nome"]).font = Font(bold=True)
            for r in range(linha, linha + 2):
                for c in range(1, ultima_col + 1):
                    cel = ws.cell(r, c)
                    cel.alignment = _CENTRO
                    cel.border = _BORDA
                    cel.fill = _TURNO[t["turno"]] if r < linha + 1 else _CINZA
            ws.row_dimensions[linha].height = 30
            linha += 2
        else:
            ws.cell(linha, 1, t["label"].upper()).font = Font(bold=True)
            ws.cell(linha + 1, 1, "Diretor")
            ws.cell(linha + 2, 1, "Horário")
            for i, col in enumerate(est, start=2):
                ws.cell(linha, i, "\n".join(col["turmas"]) or "—")
                dir_ = col.get("diretor") or {}
                ws.cell(linha + 1, i, (dir_.get("nome") or "SEM DIRETOR").upper()).font = Font(bold=True)
                ws.cell(linha + 2, i, col["estudio_nome"]).font = Font(bold=True)
            for r in range(linha, linha + 3):
                for c in range(1, ultima_col + 1):
                    cel = ws.cell(r, c)
                    cel.alignment = _CENTRO
                    cel.border = _BORDA
                    cel.fill = _TURNO[t["turno"]] if r < linha + 2 else _CINZA
            ws.row_dimensions[linha].height = 30
            linha += 3

        inicios = sorted({it["inicio"] for col in est for it in col["itens"]})
        if not inicios:
            ws.cell(linha, 1, "Sem aulas ou agendamentos").font = Font(italic=True, color="FF6B7280")
            linha += 2
            continue
        linha_de = {h: linha + i for i, h in enumerate(inicios)}
        for h, r in linha_de.items():
            cel = ws.cell(r, 1, h)
            cel.fill = _CINZA
            cel.alignment = _CENTRO
            cel.border = _BORDA
            ws.row_dimensions[r].height = 42
        ultima_linha = linha + len(inicios) - 1
        for c in range(2, ultima_col + 1):
            for r in range(linha, ultima_linha + 1):
                ws.cell(r, c).border = _BORDA

        for i, col in enumerate(est, start=2):
            ocupado_ate = linha - 1
            for it in col["itens"]:
                r_ini = linha_de[it["inicio"]]
                if r_ini <= ocupado_ate:
                    # Sobreposição na mesma coluna: acrescenta ao texto já existente
                    cel = ws.cell(r_ini, i)
                    cel.value = f"{cel.value or ''}\n———\n{it['inicio']}–{it['fim']} {_texto_item(it)}".strip()
                    continue
                abrange = [r for h, r in linha_de.items() if it["inicio"] <= h < it["fim"]]
                r_fim = max(abrange) if abrange else r_ini
                cel = ws.cell(r_ini, i, f"{it['inicio']}–{it['fim']}\n{_texto_item(it)}")
                cel.alignment = _CENTRO
                if it.get("cancelada"):
                    cel.fill = _CANCELADO
                    cel.font = Font(color="FFFFFFFF", bold=True)
                elif it.get("fantasma"):
                    cel.fill = _CINZA
                    cel.font = Font(italic=True, color="FF6B7280")
                elif it.get("cor"):
                    cel.fill = PatternFill("solid", fgColor=_clarear(it["cor"]))
                if r_fim > r_ini:
                    ws.merge_cells(start_row=r_ini, start_column=i, end_row=r_fim, end_column=i)
                ocupado_ate = r_fim
        linha = ultima_linha + 2

    if agenda.get("gravacoes_sem_horario"):
        ws.cell(linha, 1, "Gravações sem horário definido na grade").font = Font(bold=True)
        linha += 1
        for g in agenda["gravacoes_sem_horario"]:
            ws.cell(linha, 1, f"{g['turma']} — {g['disciplina'] or ''} {('· ' + g['professor']) if g['professor'] else ''}")
            linha += 1

    ws.freeze_panes = "B4"
    ws.sheet_view.zoomScale = 90


def exportar_periodo(db: Session, inicio: date, fim: date, user_role: Optional[str] = None) -> BytesIO:
    wb = Workbook()
    wb.remove(wb.active)
    d = inicio
    while d <= fim:
        ws = wb.create_sheet(d.strftime("%d-%m"))
        _aba_do_dia(ws, montar_agenda_dia(db, d), user_role=user_role)
        d += timedelta(days=1)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
