"""
Corrige o "Nº Horário" de relatórios do diretor de imagem salvos antes da numeração
pela tabela oficial (09/10/2026), quando eram contados pela posição da aula no dia.

Exemplo: turma integral cuja primeira aula do dia é às 10:50 → o relatório ficou
"1º Horário" com 10:50–11:50; pela tabela oficial esse horário é o "4º Horário".

O horário gravado (início/fim) é a referência e não muda; só o texto do Nº muda.
Sem --aplicar, apenas lista o que seria corrigido.

Uso (dentro do container da API):
    python scripts/corrigir_numeracao_horario_diretor.py --de 2026-09-01 --ate 2026-10-31
    python scripts/corrigir_numeracao_horario_diretor.py --de 2026-09-01 --ate 2026-10-31 --aplicar
"""
import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal  # noqa: E402
from app.models.image_director_report import ImageDirectorReport  # noqa: E402
from app.services.horario_resolver import ordinal_horario, ordinal_label  # noqa: E402
from app.services.image_director_slot import resolve_slot_ordinal  # noqa: E402


def encontrar(db, de: date, ate: date) -> list:
    """[(relatório, Nº gravado, Nº oficial)] dos relatórios com a numeração antiga."""
    cache: dict = {}
    corrigir = []
    q = db.query(ImageDirectorReport).filter(
        ImageDirectorReport.is_deleted == False,  # noqa: E712
        ImageDirectorReport.data_relatorio >= de,
        ImageDirectorReport.data_relatorio <= ate,
        ImageDirectorReport.turma_id.isnot(None),
        ImageDirectorReport.start_time.isnot(None),
    )
    for r in q.all():
        if (r.regular or "Sim") != "Sim" or (r.origem or "grade") != "grade":
            continue
        gravado = ordinal_horario(r.horario_aula)
        if not gravado:
            continue  # horário gravado como faixa ("10:50 às 11:50"): nada a corrigir
        oficial = resolve_slot_ordinal(db, turma_id=r.turma_id, data=r.data_relatorio, turno=r.turno,
                                       horario_aula=None, start_time=r.start_time, cache=cache)
        if oficial and oficial != gravado:
            corrigir.append((r, gravado, oficial))
    return corrigir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--de", required=True, type=date.fromisoformat)
    ap.add_argument("--ate", required=True, type=date.fromisoformat)
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        corrigir = encontrar(db, args.de, args.ate)
        print("data;turno;estudio;status;id;gravado;horario;oficial")
        for r, gravado, oficial in corrigir:
            print(f"{r.data_relatorio};{r.turno};{r.estudio};{r.status};{r.id};{gravado}º;"
                  f"{r.start_time:%H:%M}-{r.end_time:%H:%M};{oficial}º")
        print(f"\n{len(corrigir)} relatório(s) com Nº Horário pela numeração antiga.")

        if args.aplicar and corrigir:
            for r, _g, oficial in corrigir:
                r.horario_aula = ordinal_label(oficial)
            db.commit()
            print("Corrigido.")
        elif corrigir:
            print("Nada foi alterado. Rode de novo com --aplicar para corrigir.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
