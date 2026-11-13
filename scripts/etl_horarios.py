import os
import sys
import re
import pandas as pd
from datetime import datetime, time, date
from typing import Optional

# Adiciona a raiz do projeto ao path para conseguir importar a app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.turma import Turma
from app.models.auxiliares import Disciplina, Grade, Professor

def limpar_texto(texto) -> str:
    if pd.isna(texto): return ""
    return str(texto).strip()

def inferir_turno_aula(hora_inicio: time) -> str:
    minutos_totais = hora_inicio.hour * 60 + hora_inicio.minute
    if minutos_totais < (12 * 60):
        return "MANHÃ"
    elif minutos_totais < (18 * 60 + 20):
        return "TARDE"
    else:
        return "NOITE"

def parse_time(t_str: str) -> Optional[time]:
    t_str = limpar_texto(t_str).lower()
    if not t_str or t_str == "nan": return None
    if t_str == "gravação": return time(0, 0)
    
    try:
        # Formatos: "07:30", "0730", "07:30:00"
        if ":" in t_str:
            parts = t_str.split(":")
            return time(int(parts[0]), int(parts[1]))
        elif len(t_str) == 4:
            return time(int(t_str[:2]), int(t_str[2:]))
    except:
        return None
    return None

def executar_migracao(arquivo_nome: str, versao: str, data_inicio: date):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    caminho_arquivo = os.path.join(base_dir, 'data', arquivo_nome)
    
    if not os.path.exists(caminho_arquivo):
        print(f"❌ ERRO: Arquivo não encontrado em {caminho_arquivo}")
        return

    print(f"🚀 Iniciando ETL: {arquivo_nome} -> Versão: {versao}...")

    try:
        if arquivo_nome.endswith('.xlsx'):
            df = pd.read_excel(caminho_arquivo)
        else:
            df = pd.read_csv(caminho_arquivo, sep=None, engine='python')
    except Exception as e:
        print(f"❌ Erro ao ler arquivo: {e}")
        return

    db = SessionLocal()
    estatisticas = {"turmas": 0, "disciplinas": 0, "grades": 0, "professores": 0}

    # Normalizar colunas
    cols = {str(c).upper(): c for c in df.columns}

    try:
        for idx, row in df.iterrows():
            serie = limpar_texto(row.get(cols.get('SÉRIE'), row.get(cols.get('SERIE'))))
            periodo = limpar_texto(row.get(cols.get('PERIODO'), row.get(cols.get('PERÍODO'))))
            nomenclatura_turma = limpar_texto(row.get(cols.get('NOMECLATURA TURMA/TURNO'), row.get(cols.get('TURMA'))))
            horario_str = limpar_texto(row.get(cols.get('HORÁRIO'), row.get(cols.get('HORARIO'))))
            dia_semana = limpar_texto(row.get(cols.get('DIA')))
            nome_professor = limpar_texto(row.get(cols.get('PROFESSOR')))
            nome_disciplina = limpar_texto(row.get(cols.get('NOMENCLATURA'), row.get(cols.get('DISCIPLINA'))))
            iptv_str = limpar_texto(row.get(cols.get('IPTV'), row.get(cols.get('CANAL'))))
            url_iptv = limpar_texto(row.get(cols.get('URL (IPTV)'), row.get(cols.get('URL'))))

            if not serie or not horario_str: continue

            # Parsing de Horário
            h_ini, h_fim = None, None
            if horario_str.upper() == "GRAVAÇÃO":
                h_ini, h_fim = time(0, 0), time(23, 59)
                turno_aula = periodo.upper() or "GRAVAÇÃO"
            else:
                partes = re.split(r'\s*(?:às|as|-|a)\s*', horario_str.lower())
                if len(partes) == 2:
                    h_ini = parse_time(partes[0])
                    h_fim = parse_time(partes[1])
                
                if not h_ini:
                    print(f"⚠️ Linha {idx+2}: Horário inválido '{horario_str}'")
                    continue
                turno_aula = inferir_turno_aula(h_ini)

            # Entidades
            prof = None
            if nome_professor:
                prof = db.query(Professor).filter(Professor.nome == nome_professor).first()
                if not prof:
                    prof = Professor(nome=nome_professor)
                    db.add(prof); db.flush(); estatisticas["professores"] += 1

            disc = db.query(Disciplina).filter(Disciplina.nome == nome_disciplina).first()
            if not disc:
                disc = Disciplina(nome=nome_disciplina, nomenclatura_padrao=nome_disciplina[:10].upper())
                db.add(disc); db.flush(); estatisticas["disciplinas"] += 1

            turma = db.query(Turma).filter(Turma.nomenclatura_padrao == nomenclatura_turma).first()
            if not turma:
                turma = Turma(nome=f"{serie} - {periodo}", modalidade="REGULAR", serie_modulo=serie, turno=periodo.upper(), nomenclatura_padrao=nomenclatura_turma)
                db.add(turma); db.flush(); estatisticas["turmas"] += 1

            # Grade com Vigência
            nova_grade = Grade(
                turma_id=turma.id,
                disciplina_id=disc.id,
                professor_id=prof.id if prof else None,
                dia_semana=dia_semana.upper(),
                horario_inicio=h_ini,
                horario_fim=h_fim,
                turno_aula=turno_aula,
                canal_iptv=int(iptv_str) if str(iptv_str).isdigit() else None,
                descricao=url_iptv,
                vigencia_inicio=data_inicio,
                versao=versao
            )
            db.add(nova_grade)
            estatisticas["grades"] += 1

        db.commit()
        print(f"✅ Sucesso! Grades: {estatisticas['grades']}, Turmas: {estatisticas['turmas']}")
    except Exception as e:
        db.rollback()
        print(f"❌ Erro Crítico: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="horario.csv")
    parser.add_argument("--versao", default="Grade Base")
    parser.add_argument("--inicio", default="2026-01-01")
    args = parser.parse_args()
    
    executar_migracao(args.file, args.versao, datetime.strptime(args.inicio, "%Y-%m-%d").date())