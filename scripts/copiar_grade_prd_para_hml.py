"""
Copia a Grade Horária de PRODUÇÃO para HOMOLOGAÇÃO (HML).

Rodar DENTRO de um container do HML (API ou worker):

    cd /app
    python scripts/copiar_grade_prd_para_hml.py            # simulação: mostra o que vai mudar e desfaz
    python scripts/copiar_grade_prd_para_hml.py --aplicar  # grava no HML

O endereço do banco de PRD é pedido na hora (não aparece na tela) ou lido da
variável PRD_DATABASE_URL. Em PRD a conexão é SOMENTE LEITURA.

O que é copiado (PRD é a referência):
  - units, disciplinas, professores, turmas, estudio, canal_iptv, slot_horario:
      linhas de PRD entram no HML (novas são criadas, existentes são atualizadas);
      o que só existe no HML fica (relatórios antigos dependem disso).
  - grade_versao, professor_disciplinas, grades:
      ficam IGUAIS a PRD — o que só existe no HML é apagado.

Tudo roda numa única transação no HML: se der qualquer erro, nada é gravado.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

# Ordem respeitando as chaves estrangeiras
TABELAS = [
    "units", "disciplinas", "professores", "turmas",
    "estudio", "canal_iptv", "slot_horario",
    "grade_versao", "professor_disciplinas", "grades",
]
# Tabelas que ficam idênticas a PRD (apaga no HML o que não existe em PRD)
SUBSTITUIR = ["grades", "professor_disciplinas", "grade_versao"]
# grade_versao só é limpa depois que as aulas de PRD já apontam para as versões novas
LOTE = 500


def _url_hml() -> str:
    from app.core.config import get_settings
    return get_settings().DATABASE_URL


def _nome_banco(engine) -> str:
    with engine.connect() as c:
        return c.execute(sa.text("select current_database()")).scalar()


def _ler_prd(engine, meta) -> dict:
    dados = {}
    with engine.connect() as c:
        c.execute(sa.text("SET TRANSACTION READ ONLY"))
        for t in TABELAS:
            tab = meta.tables[t]
            dados[t] = [dict(r._mapping) for r in c.execute(sa.select(tab))]
        c.rollback()
    return dados


def _lotes(lista):
    for i in range(0, len(lista), LOTE):
        yield lista[i:i + LOTE]


def copiar(url_prd: str, url_hml: str, aplicar: bool) -> dict:
    prd = sa.create_engine(url_prd)
    hml = sa.create_engine(url_hml)

    banco_prd, banco_hml = _nome_banco(prd), _nome_banco(hml)
    print(f"Origem (PRD, só leitura): {banco_prd}")
    print(f"Destino (HML):            {banco_hml}")
    if banco_prd == banco_hml and url_prd == url_hml:
        raise SystemExit("PARADO: origem e destino são o mesmo banco.")
    if "prd" in banco_hml.lower() or "prod" in banco_hml.lower():
        raise SystemExit("PARADO: o destino parece ser PRODUÇÃO. Rode este script num container do HML.")

    meta_p, meta_h = sa.MetaData(), sa.MetaData()
    meta_p.reflect(prd, only=TABELAS)
    meta_h.reflect(hml, only=TABELAS + ["users", "agenda_agendamentos"])

    dados = _ler_prd(prd, meta_p)
    resumo = {}

    conn = hml.connect()
    trans = conn.begin()
    try:
        # Colunas em comum entre PRD e HML (o HML pode ter colunas a mais)
        cols = {
            t: [c.name for c in meta_h.tables[t].columns if c.name in meta_p.tables[t].columns]
            for t in TABELAS
        }
        ids_hml = {
            t: {r[0] for r in conn.execute(sa.select(meta_h.tables[t].c.id))} for t in TABELAS
        }

        # Professor com o mesmo nome e id diferente (nome é único): usa o id do HML
        mapa_prof = {}
        prof_h = {r.nome: r.id for r in conn.execute(sa.select(meta_h.tables["professores"]))}
        for p in dados["professores"]:
            if p["id"] not in ids_hml["professores"] and p["nome"] in prof_h:
                mapa_prof[p["id"]] = prof_h[p["nome"]]

        usuarios_hml = {r[0] for r in conn.execute(sa.select(meta_h.tables["users"].c.id))}

        def preparar(t, linha):
            r = {c: linha.get(c) for c in cols[t]}
            if t == "professores" and r["id"] in mapa_prof:
                r["id"] = mapa_prof[r["id"]]
            if "professor_id" in r and r.get("professor_id") in mapa_prof:
                r["professor_id"] = mapa_prof[r["professor_id"]]
            if t == "grade_versao" and r.get("criado_por") and r["criado_por"] not in usuarios_hml:
                r["criado_por"] = None
            return r

        linhas = {t: [preparar(t, l) for l in dados[t]] for t in TABELAS}

        agenda = meta_h.tables.get("agenda_agendamentos")

        def apagar_sobras(t):
            tab = meta_h.tables[t]
            sobra = ids_hml[t] - {l["id"] for l in linhas[t]}
            if t == "grades" and sobra and agenda is not None:
                resumo["agenda_sem_grade"] = conn.execute(
                    sa.select(sa.func.count()).select_from(agenda).where(agenda.c.grade_id.in_(list(sobra)))
                ).scalar()
            for lote in _lotes(list(sobra)):
                conn.execute(tab.delete().where(tab.c.id.in_(lote)))
            resumo.setdefault(t, {})["apagados"] = len(sobra)

        # 1) Apaga no HML as aulas e vínculos professor-disciplina que não existem em PRD
        apagar_sobras("grades")
        apagar_sobras("professor_disciplinas")

        # 2) Insere / atualiza a partir de PRD
        for t in TABELAS:
            tab = meta_h.tables[t]
            lista = linhas[t]
            novos = sum(1 for l in lista if l["id"] not in ids_hml[t])
            for lote in _lotes(lista):
                stmt = pg_insert(tab).values(lote)
                atualizar = {c: stmt.excluded[c] for c in cols[t] if c != "id"}
                stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=atualizar) if atualizar \
                    else stmt.on_conflict_do_nothing(index_elements=["id"])
                conn.execute(stmt)
            r = resumo.setdefault(t, {})
            r.update({"prd": len(lista), "novos": novos, "atualizados": len(lista) - novos})

        # 3) Versões de grade que só existem no HML (já sem aulas apontando para elas)
        apagar_sobras("grade_versao")

        # 4) Acerta as sequências das tabelas com id numérico
        for t in TABELAS:
            if isinstance(meta_h.tables[t].c.id.type, sa.Integer):
                conn.execute(sa.text(
                    f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {t}), 1))"
                ))

        if mapa_prof:
            resumo["professores_mesmo_nome_outro_id"] = len(mapa_prof)

        if aplicar:
            trans.commit()
        else:
            trans.rollback()
    except Exception:
        trans.rollback()
        raise
    finally:
        conn.close()
    return resumo


def main():
    ap = argparse.ArgumentParser(description="Copia a Grade Horária de PRD para o HML.")
    ap.add_argument("--aplicar", action="store_true", help="grava no HML (sem isso, só simula)")
    args = ap.parse_args()

    url_prd = os.environ.get("PRD_DATABASE_URL") or getpass.getpass(
        "Endereço do banco de PRD (postgresql://usuario:senha@host:5432/banco): "
    ).strip()
    if not url_prd:
        raise SystemExit("Informe o endereço do banco de PRD.")

    resumo = copiar(url_prd, _url_hml(), args.aplicar)

    print()
    print(f"{'Tabela':<24}{'PRD':>8}{'novos':>8}{'atualiz.':>10}{'apagados':>10}")
    for t in TABELAS:
        r = resumo.get(t, {})
        print(f"{t:<24}{r.get('prd', 0):>8}{r.get('novos', 0):>8}{r.get('atualizados', 0):>10}{r.get('apagados', 0):>10}")
    if resumo.get("professores_mesmo_nome_outro_id"):
        print(f"\nProfessores com o mesmo nome e id diferente (ligados ao do HML): {resumo['professores_mesmo_nome_outro_id']}")
    if resumo.get("agenda_sem_grade"):
        print(f"Agendamentos/remanejamentos do HML que apontavam para aulas apagadas: {resumo['agenda_sem_grade']}")
    print()
    print("GRAVADO no HML." if args.aplicar else "SIMULAÇÃO: nada foi gravado. Para gravar, rode de novo com --aplicar.")


if __name__ == "__main__":
    main()
