import sys
import os
sys.path.insert(0, "/app")

from datetime import date, time, datetime
from app.core.database import SessionLocal
from app.models.agenda_estudio import EscalaDiaEstudio, AgendamentoEstudio
from app.models.diretor_imagem import DiretorImagem
from app.models.turma import Turma
from app.models.auxiliares import Professor
from app.models.infraestrutura import Estudio
from app.models.user import User

def simular():
    db = SessionLocal()
    hoje = date.today()
    print(f"--- Iniciando simulação para a data: {hoje} ---")

    admin = db.query(User).filter(User.email == "admin@canaleducacao.com").first()
    admin_id = admin.id if admin else None

    # Obter diretores reais
    diretores = db.query(DiretorImagem).filter(DiretorImagem.is_active == True).order_by(DiretorImagem.nome).all()
    if not diretores:
        print("❌ Nenhum diretor de imagem encontrado!")
        db.close()
        return

    # Obter estúdios
    estudios = db.query(Estudio).filter(Estudio.ativo == True).order_by(Estudio.id).limit(6).all()
    
    # 1. Limpar escalas e agendamentos existentes no dia de hoje para um teste limpo
    db.query(EscalaDiaEstudio).filter(EscalaDiaEstudio.data == hoje).delete()
    db.query(AgendamentoEstudio).filter(AgendamentoEstudio.data == hoje).delete()
    db.commit()

    # 2. Escalar diretores para os estúdios nos 3 turnos
    turnos = ["manha", "tarde", "noite"]
    dir_idx = 0
    escalas_count = 0

    for est in estudios:
        for turno in turnos:
            d = diretores[dir_idx % len(diretores)]
            dir_idx += 1
            escala = EscalaDiaEstudio(
                data=hoje,
                turno=turno,
                estudio_id=est.id,
                diretor_imagem_id=d.id,
                observacao="Escala simulada",
                atualizado_por=admin_id,
                atualizado_em=datetime.utcnow()
            )
            db.add(escala)
            escalas_count += 1

    db.commit()
    print(f"✅ {escalas_count} escalas de diretores cadastradas para hoje!")

    # 3. Obter turmas reais
    turma_1 = db.query(Turma).filter(Turma.nomenclatura_padrao.ilike("%EM 1 TI%")).first()
    turma_2 = db.query(Turma).filter(Turma.nomenclatura_padrao.ilike("%EM 2 TI%")).first()
    turma_3 = db.query(Turma).filter(Turma.nomenclatura_padrao.ilike("%EM 1 NOITE%")).first()

    prof_1 = db.query(Professor).filter(Professor.nome.ilike("%Amanda%")).first()
    prof_2 = db.query(Professor).filter(Professor.nome.ilike("%Alexsandro%")).first()

    # 4. Criar agendamentos simulados
    agendamentos_dados = [
        {
            "estudio_id": estudios[0].id,
            "horario_inicio": time(8, 0),
            "horario_fim": time(9, 30),
            "tipo": "GRAVACAO_ANTECIPADA",
            "titulo": "Gravação antecipada — Física Experimental",
            "descricao": "Gravação das aulas da próxima semana do módulo experimental.",
            "professor": prof_2.nome if prof_2 else "Alexsandro Kesller",
            "turma_id": turma_1.id if turma_1 else None,
            "chamado": "CH-18920",
            "chamado_link": "https://chamados.canaleducacao.com/18920",
            "departamento": "Pedagógico",
            "status": "AGENDADO"
        },
        {
            "estudio_id": estudios[1].id,
            "horario_inicio": time(10, 0),
            "horario_fim": time(11, 30),
            "tipo": "REPOSICAO",
            "titulo": "Reposição de Aula — Matemática Aplicada",
            "descricao": "Reposição referente ao feriado anterior.",
            "professor": prof_1.nome if prof_1 else "Amanda Souza",
            "turma_id": turma_2.id if turma_2 else None,
            "chamado": "CH-18925",
            "chamado_link": "https://chamados.canaleducacao.com/18925",
            "departamento": "Pedagógico",
            "status": "AGENDADO"
        },
        {
            "estudio_id": estudios[2].id,
            "horario_inicio": time(14, 0),
            "horario_fim": time(16, 0),
            "tipo": "EVENTO",
            "titulo": "Capacitação de Professores — Novo Ensino Médio",
            "descricao": "Alinhamento metodológico com equipes escolares da rede estadual.",
            "professor": None,
            "turma_id": None,
            "chamado": "SEDUC-4401",
            "departamento": "UETEV",
            "status": "AGENDADO"
        },
        {
            "estudio_id": estudios[3].id,
            "horario_inicio": time(16, 30),
            "horario_fim": time(18, 0),
            "tipo": "PODCAST",
            "titulo": "Podcast Canal Educação — Episódio #12: Tecnologia na Sala de Aula",
            "descricao": "Gravação de bate-papo com professores e convidados especiais.",
            "professor": None,
            "turma_id": None,
            "chamado": "POD-102",
            "departamento": "Comunicação",
            "status": "AGENDADO"
        },
        {
            "estudio_id": estudios[0].id,
            "horario_inicio": time(19, 0),
            "horario_fim": time(20, 30),
            "tipo": "AULA_EXTRA",
            "titulo": "Aula Extra Noturna — EJA ETAPA V",
            "descricao": "Revisão preparatória para simulado bimestral.",
            "professor": prof_2.nome if prof_2 else "Alexsandro Kesller",
            "turma_id": turma_3.id if turma_3 else None,
            "chamado": "EXT-9901",
            "departamento": "Pedagógico",
            "status": "AGENDADO"
        },
        {
            "estudio_id": estudios[1].id,
            "horario_inicio": time(20, 45),
            "horario_fim": time(22, 0),
            "tipo": "REGRAVACAO",
            "titulo": "Regravação de Bloco — EM 1 NOITE",
            "descricao": "Regravação de bloco técnico devido a oscilação de sinal.",
            "professor": prof_1.nome if prof_1 else "Amanda Souza",
            "turma_id": turma_3.id if turma_3 else None,
            "chamado": "REG-552",
            "departamento": "Pedagógico",
            "status": "AGENDADO"
        },
    ]

    for dados in agendamentos_dados:
        ag = AgendamentoEstudio(
            data=hoje,
            estudio_id=dados["estudio_id"],
            horario_inicio=dados["horario_inicio"],
            horario_fim=dados["horario_fim"],
            tipo=dados["tipo"],
            titulo=dados["titulo"],
            descricao=dados["descricao"],
            professor=dados["professor"],
            turma_id=dados["turma_id"],
            chamado=dados["chamado"],
            chamado_link=dados.get("chamado_link"),
            departamento=dados.get("departamento"),
            status=dados["status"],
            criado_por=admin_id,
            criado_em=datetime.utcnow()
        )
        db.add(ag)

    db.commit()
    print(f"✅ {len(agendamentos_dados)} agendamentos cadastrados com sucesso!")
    db.close()

if __name__ == "__main__":
    simular()
