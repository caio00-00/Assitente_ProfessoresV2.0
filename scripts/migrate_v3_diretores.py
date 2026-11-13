import sys
import os
import json
import csv
import uuid

# Adicionar root no PYTHONPATH para imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.core.database import engine
from app.models.diretor_imagem import DiretorImagem

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def execute_migration():
    print("Iniciando Migração V3.0 - Diretores de Imagem e Professor Externo...")

    # 1. BKP dos Diretores em ClassReports (Exigência do Usuário)
    print("1. Efetuando o BKP dos diretores antigos...")
    try:
        result = db.execute(text("SELECT id, diretor_imagem FROM class_reports WHERE diretor_imagem IS NOT NULL;")).fetchall()
        backup_data = [{"report_id": str(r[0]), "diretor_antigo": r[1]} for r in result]
        
        with open('data/migration_diretores_backup.json', 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        print(f"✅ BKP concluído: {len(backup_data)} registros salvos.")
    except Exception as e:
        print(f"⚠️ Aviso no BKP (pode ser que a coluna já não exista): {str(e)}")

    # 2. Criar a nova Tabela de Diretores (se não existir)
    print("2. Criando DDL das tabelas...")
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS diretores_imagem (
                id UUID PRIMARY KEY,
                nome VARCHAR(255) UNIQUE NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_diretores_imagem_id ON diretores_imagem (id);
            CREATE INDEX IF NOT EXISTS ix_diretores_imagem_nome ON diretores_imagem (nome);
        """))
    except Exception as e:
        print(f"Erro criando tabela: {str(e)}")
        db.rollback()
        
    # 3. Lendo o CSV e Populando "diretores_imagem"
    print("3. Populando diretores do CSV...")
    csv_path = 'data/diretores_imagem.csv'
    diretores_id_map = {} # nome -> uuid
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            for row in reader:
                if row and row[0].strip():
                    nome = row[0].strip().upper()
                    # Verificar se já existe
                    exist = db.query(DiretorImagem).filter(DiretorImagem.nome == nome).first()
                    if not exist:
                        novo_id = uuid.uuid4()
                        novo_diretor = DiretorImagem(id=novo_id, nome=nome)
                        db.add(novo_diretor)
                        diretores_id_map[nome] = novo_id
                    else:
                        diretores_id_map[nome] = exist.id
        db.commit()
    print("✅ Diretores populados.")

    # 4. Alter Table em class_reports (Dropar old, Add new)
    print("4. Executando ALTER TABLE em class_reports...")
    try:
        # Verifica se 'diretor_imagem_id' já existe
        res = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='class_reports' AND column_name='diretor_imagem_id';")).fetchone()
        if not res:
            db.execute(text("ALTER TABLE class_reports ADD COLUMN diretor_imagem_id UUID REFERENCES diretores_imagem(id);"))
            db.execute(text("ALTER TABLE class_reports ADD COLUMN professor_nome_externo VARCHAR(255);"))
            db.execute(text("ALTER TABLE class_reports ALTER COLUMN professor_id DROP NOT NULL;"))
            
            # Pareamento e Update
            if 'backup_data' in locals() and backup_data:
                for bkp in backup_data:
                    nome_antigo = bkp['diretor_antigo'].strip().upper()
                    if nome_antigo in diretores_id_map:
                        d_id = diretores_id_map[nome_antigo]
                        db.execute(text(f"UPDATE class_reports SET diretor_imagem_id = '{d_id}' WHERE id = '{bkp['report_id']}';"))
            
            # Dropar coluna antiga
            db.execute(text("ALTER TABLE class_reports DROP COLUMN diretor_imagem;"))
            db.commit()
            print("✅ ALTER TABLE Concluído com Sucesso!")
        else:
            print("✅ Colunas estruturais já existem.")
            
    except Exception as e:
        print(f"❌ Erro no ALTER TABLE: {str(e)}")
        db.rollback()

if __name__ == "__main__":
    execute_migration()
