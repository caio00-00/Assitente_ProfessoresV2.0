"""
Canal Educação v4 — Prepara o banco antes da API subir.

Roda no entrypoint do container da API (e pode ser chamado à mão:
`python -m scripts.db_bootstrap`). Funciona nos três cenários que existem hoje:

1. Banco vazio (Docker local, Supabase novo): cria todas as tabelas pelos
   modelos e marca o Alembic na versão mais nova (stamp head).
2. Banco que já tem tabelas mas nunca foi marcado pelo Alembic (o caso do
   create_all que rodava no startup até a v3): marca na última versão da v3 e
   aplica só as migrações da v4.
3. Banco já marcado (HML/PRD normais): aplica as migrações pendentes.

Nos três casos, depois roda create_all (só cria tabela que falta, nunca altera
existente) e garantir_colunas_agenda — o mesmo que a API fazia ao subir — e
preenche o nome_normalizado que estiver vazio.

Um advisory lock do Postgres impede que dois containers façam isso ao mesmo tempo.
"""

import logging
import os
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

ULTIMA_REVISAO_V3 = "h0i1j2k3l4m5"
LOCK_ID = 74210431  # número fixo qualquer para o advisory lock

# Handler próprio: o alembic.ini reconfigura o logging (raiz em WARN) quando o
# Alembic roda, e as mensagens daqui sumiriam do log do container.
log = logging.getLogger("db_bootstrap")
log.setLevel(logging.INFO)
log.propagate = False
_h = logging.StreamHandler(sys.stdout)
_h.setFormatter(logging.Formatter("[db_bootstrap] %(message)s"))
log.addHandler(_h)


def _alembic_cfg(url: str) -> Config:
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(raiz, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(raiz, "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def preencher_nome_normalizado(engine) -> int:
    """Preenche class_reports.nome_normalizado onde ficou vazio.

    A migração da v4 preenche os relatórios que já existiam. Este passo cobre o
    caso de alguém voltar para a v3 por um tempo (a v3 não conhece a coluna) e
    depois subir a v4 de novo. Só olha as linhas vazias, então é rápido.
    """
    from app.utils.text_utils import normalizar_para_match

    with engine.begin() as conn:
        if "nome_normalizado" not in {c["name"] for c in inspect(conn).get_columns("class_reports")}:
            return 0
        linhas = conn.execute(text(
            "SELECT id, nome_ficheiro_gerado FROM class_reports "
            "WHERE nome_normalizado IS NULL AND nome_ficheiro_gerado IS NOT NULL"
        )).fetchall()
        for rid, nome in linhas:
            conn.execute(text("UPDATE class_reports SET nome_normalizado = :n WHERE id = :i"),
                         {"n": normalizar_para_match(nome), "i": rid})
    return len(linhas)


def preparar_banco(url: str = None) -> dict:
    """Prepara o banco (cria ou migra). Com `url`, usa essa conexão em vez da
    DATABASE_URL — a rota /api/v1/sistema/migrar passa o pooler em modo sessão
    do Supabase, porque a trava (advisory lock) não funciona no modo transação."""
    from app.core.config import get_settings
    from app.core.database import Base
    import app.models  # noqa: F401  (registra todos os modelos no metadata)
    from app.models.agenda_estudio import garantir_colunas_agenda

    if url:
        from sqlalchemy import create_engine
        from sqlalchemy.pool import NullPool

        engine = create_engine(url, poolclass=NullPool, pool_pre_ping=True)
        os.environ["DATABASE_URL"] = url  # alembic/env.py lê daqui
    else:
        from app.core.database import engine

        url = get_settings().DATABASE_URL
        os.environ.setdefault("DATABASE_URL", url)
    cfg = _alembic_cfg(url)
    resultado = {"cenario": None, "nome_normalizado_preenchido": 0}
    postgres = engine.dialect.name == "postgresql"

    with engine.connect() as conn:
        if postgres:
            conn.execute(text("SELECT pg_advisory_lock(:i)"), {"i": LOCK_ID})
        try:
            tabelas = set(inspect(conn).get_table_names())
            if "alembic_version" in tabelas:
                cenario = "marcado"
            elif "users" in tabelas:
                cenario = "legado"
            else:
                cenario = "vazio"
            log.info("cenário do banco: %s (%d tabelas)", cenario, len(tabelas))
            resultado["cenario"] = cenario

            if cenario == "vazio":
                Base.metadata.create_all(bind=engine)
                garantir_colunas_agenda(engine)
                command.stamp(cfg, "head")
                log.info("tabelas criadas e Alembic marcado em head")
            elif cenario == "legado":
                Base.metadata.create_all(bind=engine)
                garantir_colunas_agenda(engine)
                command.stamp(cfg, ULTIMA_REVISAO_V3)
                command.upgrade(cfg, "head")
                log.info("banco legado marcado em %s e atualizado para head", ULTIMA_REVISAO_V3)
            else:
                command.upgrade(cfg, "head")
                Base.metadata.create_all(bind=engine)
                garantir_colunas_agenda(engine)
                log.info("migrações aplicadas até head")
            n = preencher_nome_normalizado(engine)
            resultado["nome_normalizado_preenchido"] = n
            if n:
                log.info("nome_normalizado preenchido em %d relatório(s)", n)
        finally:
            if postgres:
                conn.execute(text("SELECT pg_advisory_unlock(:i)"), {"i": LOCK_ID})
                conn.commit()
    return resultado


def main() -> int:
    preparar_banco()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 — falha aqui tem que aparecer no log do container
        log.exception("falha ao preparar o banco")
        sys.exit(1)
