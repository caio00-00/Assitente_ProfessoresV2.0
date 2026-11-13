"""
Diagnóstico do Erro 500 em /api/v1/image-director/pdf-turno.

Roda, com os dados reais do banco, cada etapa que a rota pdf-turno executa,
uma de cada vez, e mostra o traceback completo da etapa que quebrar.
Não grava nada no banco (só leitura; faz rollback no final).

Uso (dentro do container da API):
    docker exec -it canal_edu_api python scripts/diagnostico_pdf_turno.py \
        --data 2026-10-27 --turno "Manhã" --estudio "ESTÚDIO 1" \
        --diretor d731d85d-2f51-4578-92b5-3e3ebfe542e3 \
        --turma 74a46b62-67d6-4b67-aa96-17bddaeb987d

Sem argumentos, usa o primeiro caso que deu 500 (27/10, Manhã, ESTÚDIO 1).
"""

import argparse
import sys
import traceback
from datetime import date
from types import SimpleNamespace
from uuid import UUID

sys.path.insert(0, "/app")

from app.core.database import SessionLocal  # noqa: E402
from app.api import rotas_diretor_imagem as R  # noqa: E402
from app.services import image_director_pdf as P  # noqa: E402
from app.domain.enums.enums import PAPEIS_DIRETOR_CHEFE  # noqa: E402


def titulo(txt):
    print("\n" + "=" * 70 + f"\n{txt}\n" + "=" * 70)


def etapa(nome, fn):
    """Executa uma etapa; em erro, imprime o traceback e devolve (False, None)."""
    print(f"\n>>> {nome} ... ", end="", flush=True)
    try:
        res = fn()
        print("OK")
        return True, res
    except Exception:
        print("FALHOU")
        print("-" * 70)
        traceback.print_exc()
        print("-" * 70)
        return False, None


def caracteres_fora_latin1(texto):
    if texto is None:
        return []
    return sorted({f"{c!r} (U+{ord(c):04X})" for c in str(texto) if ord(c) > 255})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="2026-10-27")
    ap.add_argument("--turno", default="Manhã")
    ap.add_argument("--estudio", default="ESTÚDIO 1")
    ap.add_argument("--diretor", default="d731d85d-2f51-4578-92b5-3e3ebfe542e3")
    ap.add_argument("--turma", default="74a46b62-67d6-4b67-aa96-17bddaeb987d")
    ap.add_argument("--dia-completo", action="store_true")
    a = ap.parse_args()

    data = date.fromisoformat(a.data)
    diretor_id = UUID(a.diretor)
    turma_id = UUID(a.turma) if a.turma else None

    db = SessionLocal()
    try:
        titulo(f"Parâmetros: data={data} turno={a.turno!r} estudio={a.estudio!r}\n"
               f"diretor={diretor_id} turma={turma_id} dia_completo={a.dia_completo}")

        # 1. Busca dos relatórios (mesma função da rota)
        ok, res = etapa("1. Buscar relatórios da grade (_fetch_grade_reports_for_pdf)", lambda: R._fetch_grade_reports_for_pdf(
            db, diretor_id, data, a.estudio,
            turno=a.turno, turma_id=turma_id, dia_completo=a.dia_completo,
        ))
        if not ok:
            return
        all_grade, is_dia_completo = res
        print(f"    {len(all_grade)} relatório(s) encontrados")
        if not all_grade:
            print("    -> a rota responderia 404 (nenhum relatório). Não é o caso do 500.")
            return

        titulo("Dados dos relatórios encontrados")
        for r in all_grade:
            print(f"\n  id={r.id}")
            print(f"    status={r.status!r} origem={r.origem!r} turno={r.turno!r} estudio={r.estudio!r}")
            print(f"    horario_aula={r.horario_aula!r} regular={r.regular!r} start={r.start_time} end={r.end_time}")
            print(f"    turma_nome={r.turma_nome!r} serie_manual={r.serie_modulo_manual!r}")
            print(f"    diretor={r.diretor_imagem_nome!r} professor={r.professor_nome!r}")
            print(f"    aulas (lessons)={len(r.lessons)} numeros={[l.numero_aula for l in r.lessons]}")
            print(f"    checklist={len(r.checklist_respostas)} respostas_extras={len(r.respostas_extras)}")
            for campo in ("turma_nome", "estudio", "serie_modulo_manual"):
                fora = caracteres_fora_latin1(getattr(r, campo, None))
                if fora:
                    print(f"    !!! {campo} tem caracteres fora do latin-1: {fora}")

        finalized = [r for r in all_grade if r.status in R.FINALIZED_IMAGE_STATUSES]
        print(f"\n  Finalizados (entram no PDF): {len(finalized)}")
        if not finalized:
            print("    -> a rota responderia 400 (nenhum finalizado). Não é o caso do 500.")
            return

        # 2. Horários de exibição
        ok, _ = etapa("2. Resolver horários (_attach_display_times)", lambda: R._attach_display_times(db, finalized))
        if not ok:
            return
        for r in finalized:
            print(f"    {r.id}: _slot_times={r._slot_times} _slot_ordinal={r._slot_ordinal}")

        # 3. Contexto do template
        ok, ctx = etapa("3. Montar contexto (build_turno_context)", lambda: P.build_turno_context(finalized, dia_completo=is_dia_completo))
        if not ok:
            return

        # 4. Renderizar HTML
        def _html():
            ctx["request"] = None
            return P._templates().get_template("image_director_turno_pdf.html").render(ctx)
        ok, html = etapa("4. Renderizar HTML do template", _html)
        if not ok:
            return

        # 5. HTML -> PDF (xhtml2pdf)
        def _pisa():
            import io
            from xhtml2pdf import pisa
            out = io.BytesIO()
            result = pisa.CreatePDF(src=html, dest=out, encoding="utf-8")
            if result.err:
                raise RuntimeError(f"xhtml2pdf retornou err={result.err}. Veja o log acima.")
            return out.getvalue()
        ok, pdf = etapa("5. Converter HTML em PDF (xhtml2pdf)", _pisa)
        if not ok:
            with open("/tmp/diagnostico_pdf_turno.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("    HTML salvo em /tmp/diagnostico_pdf_turno.html (dentro do container)")
            return

        # 6. Timbrado
        ok, pdf_final = etapa("6. Aplicar timbrado (_apply_letterhead / pypdf)", lambda: P._apply_letterhead(pdf))
        if not ok:
            return

        # 7. Nome do arquivo + cabeçalho HTTP
        ok, nome = etapa("7. Gerar nome do arquivo (_pdf_filename)", lambda: R._pdf_filename(finalized[0]))
        if not ok:
            return
        print(f"    nome={nome!r}")

        def _header():
            from fastapi.responses import Response
            return Response(
                content=pdf_final,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{nome}"'},
            )
        ok, _ = etapa("8. Montar resposta HTTP (Content-Disposition)", _header)
        if not ok:
            print(f"    caracteres problemáticos no nome: {caracteres_fora_latin1(nome)}")
            return

        # 9. Rota inteira, do jeito que o navegador chama (como diretor-chefe)
        chefe = SimpleNamespace(role=next(iter(PAPEIS_DIRETOR_CHEFE)), id=None, full_name="diagnostico")
        ok, _ = etapa("9. Chamar a rota download_turno_pdf inteira", lambda: R.download_turno_pdf(
            request=None, data=data, estudio=a.estudio, turno=a.turno, turma_id=turma_id,
            dia_completo=a.dia_completo, diretor_imagem_id=diretor_id, report_id=None,
            db=db, current_user=chefe,
        ))
        if ok:
            titulo("Tudo passou aqui. Se o navegador ainda dá 500, o erro está fora desta rota\n"
                   "(ex.: versão de código diferente no servidor). Mande o docker logs.")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
