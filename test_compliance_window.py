"""
Teste standalone da janela de re-verificação automática de compliance (~45 dias).

Este teste NÃO importa o projeto real (evita depender de config/DB de produção).
Ele recria, em SQLite em memória, apenas as colunas de ClassReport relevantes
para o filtro, e replica exatamente a MESMA condição de data usada nos jobs
`sincronizacao_noturna_drive` e `reprocessar_vermelhos_drive` após o ajuste:

    ClassReport.data_aula >= (hoje - timedelta(days=COMPLIANCE_MAX_AGE_DAYS))

Cenário:
- report_abril: data_aula em 15/04/2026 (fora da janela de 45 dias a partir de
  hoje, 07/08/2026) -> NÃO deve entrar na lista de reprocessamento automático.
- report_agosto: data_aula em 01/08/2026 (dentro da janela) -> DEVE entrar.

Para rodar:
    pytest -v test_compliance_window.py
"""

import datetime as dt

import pytest
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    String,
    create_engine,
    or_,
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

COMPLIANCE_MAX_AGE_DAYS = 45

# "Hoje" fixo para o teste ser determinístico (equivalente à data atual real,
# 2026-08-07, usada na conversa). Ajuste aqui se rodar em outra data de verdade.
HOJE = dt.date(2026, 8, 7)


class ClassReportFake(Base):
    """Réplica mínima das colunas de ClassReport usadas no filtro de compliance."""

    __tablename__ = "class_report"

    id = Column(String, primary_key=True)
    data_aula = Column(Date, nullable=False)
    status = Column(String, nullable=False)
    status_compliance = Column(String, nullable=True)
    is_deleted = Column(Boolean, default=False)
    nome_ficheiro_gerado = Column(String, nullable=True)
    video_link = Column(String, nullable=True)
    slide_link = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=True)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Relatório antigo (abril) — fora da janela de 45 dias, sem vídeo/slide,
    # status Vermelho (já esgotou os retries no passado).
    db.add(
        ClassReportFake(
            id="report-abril",
            data_aula=dt.date(2026, 4, 15),
            status="FINALIZADO",
            status_compliance="Vermelho",
            is_deleted=False,
            nome_ficheiro_gerado="EM3MANHAQUIMICA150426.mp4",
            video_link=None,
            slide_link=None,
            created_at=dt.datetime(2026, 4, 15, 12, 0, 0),
        )
    )

    # Relatório recente (agosto) — dentro da janela de 45 dias, ainda Pendente.
    db.add(
        ClassReportFake(
            id="report-agosto",
            data_aula=dt.date(2026, 8, 1),
            status="FINALIZADO",
            status_compliance="Pendente",
            is_deleted=False,
            nome_ficheiro_gerado="EM3MANHAQUIMICA010826.mp4",
            video_link=None,
            slide_link=None,
            created_at=dt.datetime(2026, 8, 1, 12, 0, 0),
        )
    )

    db.commit()
    yield db
    db.close()


def _query_sincronizacao_noturna(db, hoje: dt.date, max_age_days: int):
    """Replica a query de sincronizacao_noturna_drive() após o ajuste."""
    data_limite = hoje - dt.timedelta(days=max_age_days)
    return (
        db.query(ClassReportFake)
        .filter(
            or_(
                ClassReportFake.video_link == None,  # noqa: E711
                ClassReportFake.slide_link == None,  # noqa: E711
            )
        )
        .filter(ClassReportFake.nome_ficheiro_gerado != None)  # noqa: E711
        .filter(ClassReportFake.is_deleted == False)  # noqa: E712
        .filter(ClassReportFake.status == "FINALIZADO")
        .filter(ClassReportFake.data_aula >= data_limite)
        .all()
    )


def _query_reprocessar_vermelhos(db, hoje: dt.date, max_age_days: int):
    """Replica a query de reprocessar_vermelhos_drive() após o ajuste."""
    data_limite_idade = hoje - dt.timedelta(days=max_age_days)
    return (
        db.query(ClassReportFake)
        .filter(
            ClassReportFake.status_compliance.in_(["Vermelho", "Pendente"]),
            ClassReportFake.nome_ficheiro_gerado.isnot(None),
            ClassReportFake.is_deleted == False,  # noqa: E712
            ClassReportFake.status == "FINALIZADO",
            ClassReportFake.data_aula >= data_limite_idade,
            or_(
                ClassReportFake.video_link.is_(None),
                ClassReportFake.slide_link.is_(None),
            ),
        )
        .all()
    )


def test_sincronizacao_noturna_exclui_relatorio_fora_da_janela(session):
    resultados = _query_sincronizacao_noturna(session, HOJE, COMPLIANCE_MAX_AGE_DAYS)
    ids = {r.id for r in resultados}

    assert "report-agosto" in ids, "Relatório recente deveria entrar na sincronização"
    assert "report-abril" not in ids, "Relatório de abril NÃO deveria mais ser re-verificado automaticamente"


def test_reprocessar_vermelhos_exclui_relatorio_fora_da_janela(session):
    resultados = _query_reprocessar_vermelhos(session, HOJE, COMPLIANCE_MAX_AGE_DAYS)
    ids = {r.id for r in resultados}

    assert "report-agosto" in ids, "Relatório recente (Pendente) deveria ser re-checado pelo safety-net"
    assert "report-abril" not in ids, "Relatório de abril (Vermelho) NÃO deveria mais ser resetado/re-enfileirado"


def test_relatorio_no_limite_exato_da_janela_ainda_entra(session):
    # Relatório com data_aula exatamente 45 dias atrás -> deve ENTRAR (>=).
    limite = HOJE - dt.timedelta(days=COMPLIANCE_MAX_AGE_DAYS)
    session.add(
        ClassReportFake(
            id="report-limite",
            data_aula=limite,
            status="FINALIZADO",
            status_compliance="Pendente",
            is_deleted=False,
            nome_ficheiro_gerado="LIMITE.mp4",
            video_link=None,
            slide_link=None,
            created_at=dt.datetime.combine(limite, dt.time(12, 0)),
        )
    )
    session.commit()

    resultados = _query_reprocessar_vermelhos(session, HOJE, COMPLIANCE_MAX_AGE_DAYS)
    ids = {r.id for r in resultados}
    assert "report-limite" in ids

    # Um dia mais velho que o limite -> deve FICAR DE FORA.
    session.query(ClassReportFake).filter_by(id="report-limite").update(
        {"data_aula": limite - dt.timedelta(days=1)}
    )
    session.commit()

    resultados = _query_reprocessar_vermelhos(session, HOJE, COMPLIANCE_MAX_AGE_DAYS)
    ids = {r.id for r in resultados}
    assert "report-limite" not in ids