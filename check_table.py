import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def check_table_structure():
    db = SessionLocal()
    try:
        print("\n=== ESTRUTURA DA TABELA GRADES ===")
        q = text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'grades'
            ORDER BY ordinal_position;
        """)
        res = db.execute(q).fetchall()
        for row in res:
            print(f"Coluna: {row[0]:<25} | Tipo: {row[1]}")

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_table_structure()
