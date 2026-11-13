"""
Agenda de Estúdios — substitui a "PLANILHA AGENDAMENTO ESTÚDIOS".

A grade horária (tabela ``grades``) já diz qual turma/disciplina ocupa cada
estúdio em cada horário. O que a planilha tinha a mais, e que vive aqui:

* EscalaFixaEstudio  — diretor de imagem padrão de cada estúdio, por dia da
  semana e turno (o nome que ia no topo de cada coluna da planilha).
* EscalaDiaEstudio   — troca pontual do diretor num dia específico
  (ou "sem diretor" nesse dia).
* AgendamentoEstudio — o que entrava por fora da grade: gravações antecipadas,
  reposições, assíncronas, reservas, manutenção… com nº do chamado.
  O tipo AULA_CANCELADA marca uma aula da grade como cancelada numa data
  (as células vermelhas da planilha).
"""

import json
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, ForeignKey, Integer, String, Text, Time, TIMESTAMP, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class EscalaFixaEstudio(Base):
    __tablename__ = "agenda_escala_fixa"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dia_semana = Column(Integer, nullable=False)  # 0=Segunda … 6=Domingo
    turno = Column(String(10), nullable=False)    # manha | tarde | noite
    estudio_id = Column(Integer, ForeignKey("estudio.id"), nullable=False)
    diretor_imagem_id = Column(UUID(as_uuid=True), ForeignKey("diretores_imagem.id"), nullable=False)
    atualizado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    atualizado_em = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    diretor = relationship("DiretorImagem")

    __table_args__ = (
        UniqueConstraint("dia_semana", "turno", "estudio_id", name="uq_agenda_escala_fixa"),
    )


class EscalaDiaEstudio(Base):
    __tablename__ = "agenda_escala_dia"

    id = Column(Integer, primary_key=True, autoincrement=True)
    data = Column(Date, nullable=False, index=True)
    turno = Column(String(10), nullable=False)
    estudio_id = Column(Integer, ForeignKey("estudio.id"), nullable=False)
    # None = estúdio sem diretor neste dia (mesmo que a escala fixa tenha alguém)
    diretor_imagem_id = Column(UUID(as_uuid=True), ForeignKey("diretores_imagem.id"), nullable=True)
    # Segundo diretor no mesmo estúdio e turno (ex.: o primeiro passou mal e outro assumiu)
    diretor2_imagem_id = Column(UUID(as_uuid=True), ForeignKey("diretores_imagem.id"), nullable=True)
    troca_horario = Column(Time, nullable=True)  # hora em que o segundo diretor assumiu
    # Todas as trocas do turno, em ordem: [{"diretor_imagem_id": "...", "a_partir": "HH:MM"}, ...]
    # (o 2º diretor acima é sempre a primeira troca; eventos longos podem ter 3º, 4º…)
    trocas_json = Column(Text, nullable=True)
    # Transmissão do estúdio no turno: o diretor-chefe informa, o diretor escalado copia
    youtube_link = Column(String(500), nullable=True)
    chave_transmissao = Column(String(255), nullable=True)
    observacao = Column(String(255), nullable=True)
    atualizado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    atualizado_em = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    diretor = relationship("DiretorImagem", foreign_keys=[diretor_imagem_id])
    diretor2 = relationship("DiretorImagem", foreign_keys=[diretor2_imagem_id])

    __table_args__ = (
        UniqueConstraint("data", "turno", "estudio_id", name="uq_agenda_escala_dia"),
    )

    def trocas(self) -> list:
        """Diretores que assumiram depois do primeiro, em ordem de horário."""
        if self.trocas_json:
            try:
                lista = json.loads(self.trocas_json)
                if isinstance(lista, list):
                    return [t for t in lista if t.get("diretor_imagem_id")]
            except ValueError:
                pass
        if self.diretor2_imagem_id:
            return [{
                "diretor_imagem_id": str(self.diretor2_imagem_id),
                "a_partir": self.troca_horario.strftime("%H:%M") if self.troca_horario else None,
            }]
        return []


class AgendamentoEstudio(Base):
    __tablename__ = "agenda_agendamentos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data = Column(Date, nullable=False, index=True)
    estudio_id = Column(Integer, ForeignKey("estudio.id"), nullable=False)
    horario_inicio = Column(Time, nullable=False)
    horario_fim = Column(Time, nullable=False)

    tipo = Column(String(30), nullable=False)
    titulo = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    professor = Column(String(255), nullable=True)
    turma_id = Column(UUID(as_uuid=True), ForeignKey("turmas.id"), nullable=True)
    # Para AULA_CANCELADA / AULA_REMANEJADA: a aula da grade afetada nesta data
    # (REMANEJADA: estudio_id é o estúdio para onde a aula foi neste dia)
    # (SET NULL: se o slot for apagado da grade, o registro fica e aparece na conferência)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True, index=True)

    chamado = Column(String(50), nullable=True)
    chamado_link = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="AGENDADO")  # AGENDADO | CANCELADO
    # Canal SEDUC-PI usado (gravação, evento, aula remanejada…)
    canal_iptv_id = Column(Integer, ForeignKey("canal_iptv.id"), nullable=True)
    # Quem pediu (evento): UETEV, SUGED, departamento…
    departamento = Column(String(120), nullable=True)

    # v3.5 — demandas outubro 2026 (eventos, chave, antecipação e mês de referência)
    chave_transmissao = Column(String(255), nullable=True)
    nome_evento = Column(String(255), nullable=True)
    responsavel_evento = Column(String(255), nullable=True)
    solicitante_antecipacao = Column(String(20), nullable=True)  # SEDUC / PROFESSOR
    data_referencia = Column(Date, nullable=True)
    motivo_referencia = Column(String(255), nullable=True)
    # Gravação marcada como reposição: data_referencia = a aula que não aconteceu (antes da gravação)
    reposicao = Column(Boolean, nullable=False, default=False, server_default="false")
    # Gravação ligada a uma aula da grade (na data_referencia): a que vai ao ar com ela
    # (antecipada) ou a que ela repõe (reposição)
    grade_exibicao_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True)

    criado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    criado_em = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    atualizado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    atualizado_em = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    estudio = relationship("Estudio")
    turma = relationship("Turma")
    grade = relationship("Grade", foreign_keys=[grade_id])
    grade_exibicao = relationship("Grade", foreign_keys=[grade_exibicao_id])
    canal = relationship("CanalIptvModel")


class BloqueioEstudio(Base):
    """
    Horário trancado (o "laranja" da planilha): período recorrente em que o
    estúdio não recebe agendamento — ex.: fim da tarde dos estúdios cuja
    noite começa às 18:00.
    """
    __tablename__ = "agenda_bloqueios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    estudio_id = Column(Integer, ForeignKey("estudio.id"), nullable=False)
    dias_semana = Column(String(20), nullable=False, default="0,1,2,3,4")  # "0,1,2" (0=Segunda)
    horario_inicio = Column(Time, nullable=False)
    horario_fim = Column(Time, nullable=False)
    motivo = Column(String(255), nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)
    # TRANCADO: o estúdio não recebe agendamento (só se a direção liberar).
    # SOB_DEMANDA: horário livre, mas só abre com um mínimo de aulas (não compensa
    # chamar diretor horista/PJ para uma aula só).
    tipo = Column(String(20), nullable=False, default="TRANCADO")
    minimo_aulas = Column(Integer, nullable=True)
    atualizado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    atualizado_em = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    estudio = relationship("Estudio")

    def dias(self):
        return {int(d) for d in (self.dias_semana or "").split(",") if d.strip().isdigit()}


class FeriadoAgenda(Base):
    """Dia marcado como feriado: a agenda inteira fica trancada nesse dia."""
    __tablename__ = "agenda_feriados"

    id = Column(Integer, primary_key=True, autoincrement=True)
    data = Column(Date, nullable=False, unique=True, index=True)
    nome = Column(String(120), nullable=False)
    criado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    criado_em = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)


class ObservacaoAgenda(Base):
    """
    Observação num bloco da agenda (aula da grade num dia, ou agendamento):
    quantas forem precisas, com link do TomTicket quando houver.
    """
    __tablename__ = "agenda_observacoes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    data = Column(Date, nullable=False, index=True)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True, index=True)
    agendamento_id = Column(UUID(as_uuid=True), ForeignKey("agenda_agendamentos.id", ondelete="CASCADE"),
                            nullable=True, index=True)
    texto = Column(Text, nullable=False)
    link = Column(String(500), nullable=True)
    autor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    autor_nome = Column(String(255), nullable=True)
    criado_em = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)


class ConfigEstudioAgenda(Base):
    """O que a agenda precisa saber de cada estúdio para sugerir remanejamento."""
    __tablename__ = "agenda_estudio_config"

    estudio_id = Column(Integer, ForeignKey("estudio.id"), primary_key=True)
    libras = Column(Boolean, nullable=False, default=False)       # estúdio preparado para Libras
    prioridade_evento = Column(Integer, nullable=True)            # 1 = primeira opção para evento
    atualizado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    atualizado_em = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class IntervaloAgenda(Base):
    """
    Intervalo (pausa) do turno nos estúdios, com vigência: cada mudança vale do
    dia escolhido em diante (ou só naquele dia) e os dias que já passaram ficam
    com o intervalo que tinham. ``estudio_id`` vazio = padrão de todos os
    estúdios; preenchido = exceção daquele estúdio (ex.: Estúdio 4). Horário
    vazio: no padrão, "sem intervalo"; no estúdio, "segue o padrão".
    """
    __tablename__ = "agenda_intervalos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    turno = Column(String(10), nullable=False, index=True)          # manha | tarde
    estudio_id = Column(Integer, ForeignKey("estudio.id"), nullable=True, index=True)
    horario_inicio = Column(Time, nullable=True)
    horario_fim = Column(Time, nullable=True)
    vigente_desde = Column(Date, nullable=False, index=True)
    vigente_ate = Column(Date, nullable=True)                        # preenchido = só naquele dia
    motivo = Column(String(255), nullable=True)
    criado_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    criado_por_nome = Column(String(255), nullable=True)
    criado_em = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    estudio = relationship("Estudio")


# Valores fixos dos intervalos (reunião de 06/11/2026). Entram uma vez só, valendo a partir
# do dia em que esta versão sobe; daí em diante quem muda é o diretor-chefe, pela agenda.
INTERVALOS_FIXOS = {
    ("manha", None): ("09:30", "09:50"),
    ("tarde", None): ("14:50", "15:10"),
    ("manha", 4): ("10:00", "10:20"),
    ("tarde", 4): ("16:00", "16:20"),
}


def _numero_estudio(nome) -> int | None:
    import re
    m = re.search(r"(\d+)", str(nome or ""))
    return int(m.group(1)) if m else None


def semear_intervalos(engine, hoje=None) -> int:
    """Grava cada intervalo fixo que ainda não existe (padrão e Estúdio 4). Devolve quantos gravou."""
    from datetime import date as _date, time as _time

    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from sqlalchemy import inspect

    tabelas = set(inspect(engine).get_table_names())
    if not {"agenda_intervalos", "estudio"} <= tabelas:
        return 0
    hoje = hoje or _date.today()
    with Session(engine) as db:
        estudios = db.execute(text("SELECT id, nome FROM estudio")).fetchall()
        por_numero = {}
        for est_id, nome in estudios:
            por_numero.setdefault(_numero_estudio(nome), est_id)
        n = 0
        for (turno, numero), (ini, fim) in INTERVALOS_FIXOS.items():
            est_id = None
            if numero is not None:
                est_id = por_numero.get(numero)
                if est_id is None:
                    continue
            ja_tem = db.query(IntervaloAgenda.id).filter(
                IntervaloAgenda.turno == turno,
                IntervaloAgenda.estudio_id.is_(None) if est_id is None else IntervaloAgenda.estudio_id == est_id,
            ).first()
            if ja_tem:  # já gravado (ou já mudado pelo diretor-chefe): não mexe
                continue
            h1, m1 = map(int, ini.split(":")); h2, m2 = map(int, fim.split(":"))
            db.add(IntervaloAgenda(turno=turno, estudio_id=est_id, horario_inicio=_time(h1, m1),
                                   horario_fim=_time(h2, m2), vigente_desde=hoje,
                                   motivo="Valor fixo inicial", criado_por_nome="Sistema"))
            n += 1
        db.commit()
        return n


def garantir_colunas_agenda(engine) -> None:
    """
    As tabelas da agenda são criadas pelo create_all; colunas acrescentadas
    depois (canal, departamento) não. Adiciona as que faltarem — só colunas
    opcionais, sem mexer em dados.
    """
    from sqlalchemy import inspect, text

    novas = {
        "agenda_agendamentos": {
            "canal_iptv_id": "INTEGER REFERENCES canal_iptv(id)",
            "departamento": "VARCHAR(120)",
            "grade_exibicao_id": "UUID REFERENCES grades(id) ON DELETE SET NULL",
            "reposicao": "BOOLEAN NOT NULL DEFAULT FALSE",
        },
        "agenda_bloqueios": {
            "tipo": "VARCHAR(20) NOT NULL DEFAULT 'TRANCADO'",
            "minimo_aulas": "INTEGER",
        },
        "agenda_escala_dia": {
            "diretor2_imagem_id": "UUID REFERENCES diretores_imagem(id)",
            "troca_horario": "TIME",
            "youtube_link": "VARCHAR(500)",
            "chave_transmissao": "VARCHAR(255)",
            "trocas_json": "TEXT",
        },
    }
    insp = inspect(engine)
    tabelas = set(insp.get_table_names())
    if engine.dialect.name == "sqlite":  # testes: tipos equivalentes no SQLite
        novas["agenda_escala_dia"]["diretor2_imagem_id"] = "VARCHAR(36)"
        novas["agenda_agendamentos"]["grade_exibicao_id"] = "VARCHAR(36)"
        novas["agenda_agendamentos"]["reposicao"] = "BOOLEAN NOT NULL DEFAULT 0"
    with engine.begin() as conn:
        for tabela, colunas in novas.items():
            if tabela not in tabelas:
                continue
            existentes = {c["name"] for c in insp.get_columns(tabela)}
            for nome, tipo in colunas.items():
                if nome not in existentes:
                    conn.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}"))
    converter_tipos_de_gravacao(engine)
    semear_intervalos(engine)


# Reunião (26/10/2026): os tipos de gravação viraram um só, "Gravação"; reposição virou marcação.
TIPOS_ANTIGOS_DE_GRAVACAO = {
    "GRAVACAO_ANTECIPADA": "Gravação antecipada",
    "CURSO_TECNICO": "Gravação curso técnico",
    "REGRAVACAO": "Regravação",
    "ASSINCRONA": "Assíncrona / NP",
    "REPOSICAO": "Reposição",
}


def converter_tipos_de_gravacao(engine) -> int:
    """
    Converte os agendamentos antigos para o tipo "Gravação", guardando o tipo antigo na
    descrição ("[tipo antigo: Regravação]"). Reposição vira Gravação + marcação de reposição.
    Pode rodar várias vezes: só mexe no que ainda está com tipo antigo.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "agenda_agendamentos" not in set(insp.get_table_names()):
        return 0
    colunas = {c["name"] for c in insp.get_columns("agenda_agendamentos")}
    if not {"tipo", "reposicao", "descricao"} <= colunas:
        return 0
    total = 0
    with engine.begin() as conn:
        for antigo, rotulo in TIPOS_ANTIGOS_DE_GRAVACAO.items():
            res = conn.execute(
                text(
                    "UPDATE agenda_agendamentos SET tipo = 'GRAVACAO', "
                    "reposicao = :rep, "
                    "descricao = TRIM(COALESCE(descricao, '') || :marca) "
                    "WHERE tipo = :antigo"
                ),
                {"rep": antigo == "REPOSICAO", "marca": f" [tipo antigo: {rotulo}]", "antigo": antigo},
            )
            total += res.rowcount or 0
    return total
