import os
import sys
from sqlalchemy import text

# Adicionar pasta raiz ao path para importar app.core.database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal

def migrate_v3():
    db = SessionLocal()
    try:
        print("Iniciando migração v3.0 em class_reports...")
        
        # Array of queries to add columns if they don't exist
        columns = [
            "escolas_participantes JSONB DEFAULT NULL",
            "diretor_imagem VARCHAR(255) DEFAULT 'Não Informado'",
            "youtube_link VARCHAR(1000) DEFAULT NULL",
            "ticket_number VARCHAR(100) DEFAULT NULL",
            "needs_editing BOOLEAN DEFAULT FALSE NOT NULL",
            "start_time TIME DEFAULT NULL",
            "end_time TIME DEFAULT NULL",
            "problematic_materials JSONB DEFAULT NULL",
            "observacoes_manha TEXT DEFAULT NULL"
        ]

        for col in columns:
            col_name = col.split(" ")[0]
            try:
                db.execute(text(f"ALTER TABLE class_reports ADD COLUMN {col};"))
                print(f"✅ Coluna '{col_name}' adicionada com sucesso.")
            except Exception as e:
                # Caso a coluna já exista, a query vai falhar.
                db.rollback()
                print(f"⚠️  Aviso: não foi possível adicionar '{col_name}' (pode já existir).")
            else:
                db.commit()

        print("Migração v3.0 finalizada.")
    finally:
        db.close()

if __name__ == "__main__":
    migrate_v3()
