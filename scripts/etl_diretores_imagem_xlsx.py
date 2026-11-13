"""
Canal Educação v3.0 — ETL: Diretores de Imagem (a partir do Excel)
Lê o arquivo 'diretores de imagem.xlsx' e insere os diretores na tabela 'diretores_imagem'.
Similar ao padrão dos demais scripts em /scripts.
"""

import os
import sys
import uuid

# Adiciona a raiz do projeto ao sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import openpyxl
except ImportError:
    print("Instalando openpyxl...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
    import openpyxl

from sqlalchemy.orm import sessionmaker
from app.core.database import engine
from app.models.diretor_imagem import DiretorImagem

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def run_etl():
    """Realiza a ingestão dos diretores de imagem do arquivo Excel no banco de dados."""
    
    # Caminho do arquivo Excel (pode estar na raiz do projeto)
    xlsx_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'data', 'diretores de imagem.xlsx')
    )
    
    if not os.path.exists(xlsx_path):
        print(f"❌ Arquivo não encontrado: {xlsx_path}")
        return
    
    print(f"📂 Lendo arquivo: {xlsx_path}")
    
    # Ler a planilha
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb.active
    
    # Extrair nomes (coluna A)
    nomes = []
    for row in ws.iter_rows(min_row=1, values_only=True):
        if row[0] is not None:
            nome = str(row[0]).strip().upper()
            if nome:
                nomes.append(nome)
    
    wb.close()
    
    print(f"📋 Encontrados {len(nomes)} nomes no Excel.")
    
    if not nomes:
        print("⚠️ Nenhum nome encontrado. Verifique o arquivo.")
        return
    
    # Inserção no banco
    session = SessionLocal()
    novos = 0
    existentes = 0
    
    try:
        # Buscar nomes já cadastrados
        existing_names = set(
            nome for (nome,) in session.query(DiretorImagem.nome).all()
        )
        
        for nome in nomes:
            if nome not in existing_names:
                novo_diretor = DiretorImagem(
                    id=uuid.uuid4(),
                    nome=nome,
                )
                session.add(novo_diretor)
                existing_names.add(nome)
                novos += 1
            else:
                existentes += 1
        
        session.commit()
        
        print(f"\n✅ ETL concluído com sucesso!")
        print(f"   📥 Novos diretores inseridos: {novos}")
        print(f"   ♻️ Já existentes (ignorados): {existentes}")
        print(f"   📊 Total na tabela: {len(existing_names)}")
        
    except Exception as e:
        session.rollback()
        print(f"\n❌ Erro durante a inserção: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    print("=" * 60)
    print("  ETL: Diretores de Imagem (Excel → PostgreSQL)")
    print("=" * 60)
    run_etl()
