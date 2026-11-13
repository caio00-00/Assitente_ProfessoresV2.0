#!/usr/bin/env python3
"""
Diagnóstico do erro 500 em GET /api/v1/reports/
Rodar no container da API: python scripts/diag_reports_api.py
"""
from sqlalchemy import inspect

from app.core.database import SessionLocal, engine
from app.models.class_report import ClassReport
from app.schemas.class_report import ClassReportResponse, PaginatedReportsResponse

REQUIRED_COLUMNS = [
    "precisa_correcao",
    "observacao_coordenacao",
    "validado_por",
    "validado_em",
    "vimeo_link",
    "is_deleted",
    "diretor_imagem_id",
    "youtube_link",
    "bncc_habilidades",
    "slide_link",
]


def main() -> None:
    print("=== Colunas em class_reports ===")
    cols = {c["name"] for c in inspect(engine).get_columns("class_reports")}
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    for c in REQUIRED_COLUMNS:
        print(f"  {c}: {'OK' if c in cols else 'FALTA'}")
    if missing:
        print(f"\nERRO: faltam colunas: {missing}")
        print("Rode: alembic current && alembic upgrade head")
        return

    status_col = next(c for c in inspect(engine).get_columns("class_reports") if c["name"] == "status")
    print(f"\nstatus VARCHAR length: {getattr(status_col.get('type'), 'length', '?')}")

    print("\n=== Query + serialização (como a API) ===")
    db = SessionLocal()
    try:
        q = db.query(ClassReport).filter(ClassReport.is_deleted == False)  # noqa: E712
        total = q.count()
        print(f"Total relatórios (não deletados): {total}")

        items = q.order_by(ClassReport.data_aula.desc()).limit(50).all()
        print(f"Amostra: {len(items)} registros")

        failed = 0
        for i, row in enumerate(items):
            try:
                ClassReportResponse.model_validate(row)
            except Exception as e:
                failed += 1
                print(f"  [{i}] FALHA id={row.id} data={row.data_aula}: {e}")

        if failed == 0:
            PaginatedReportsResponse(items=items, total=total, limit=50, offset=0)
            print("\nOK: query e PaginatedReportsResponse passaram.")
        else:
            print(f"\nERRO: {failed} registro(s) falharam na serialização (causa provável do 500).")
    except Exception as e:
        print(f"\nERRO na query SQL: {type(e).__name__}: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
