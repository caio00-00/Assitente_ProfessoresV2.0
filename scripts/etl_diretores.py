import os
import sys
import csv

# Adiciona a raiz do projeto ao sys.path para importações do pacote app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import Column, Integer, String
from app.core.database import SessionLocal, engine, Base

class DiretorImagem(Base):
    __tablename__ = "diretores_imagem"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True, nullable=False)

def run_etl():
    # Cria a tabela se não existir (o `checkfirst=True` é o padrão)
    DiretorImagem.__table__.create(bind=engine, checkfirst=True)

    file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'diretores_imagem.csv'))
    
    if not os.path.exists(file_path):
        print(f"Erro: Arquivo não encontrado - {file_path}")
        return

    novos_diretores = 0
    session = SessionLocal()
    
    try:
        # Obtém os nomes já cadastrados para evitar duplicatas e consultas repetidas (upsert)
        existing_names = set(nome for (nome,) in session.query(DiretorImagem.nome).all())
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            for row in reader:
                if not row:
                    continue
                
                raw_nome = row[0]
                if not raw_nome:
                    continue
                
                # Limpa espaços em branco extras
                nome = raw_nome.strip()
                if not nome:
                    continue
                
                # Somente adiciona se ainda não estiver cadastrado
                if nome not in existing_names:
                    novo_diretor = DiretorImagem(nome=nome)
                    session.add(novo_diretor)
                    existing_names.add(nome)
                    novos_diretores += 1
        
        session.commit()
        print(f"ETL concluído com sucesso. {novos_diretores} novos diretores foram adicionados.")
    except Exception as e:
        session.rollback()
        print(f"Erro durante a execução do ETL: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    print("Iniciando o script de ETL de Diretores...")
    run_etl()
