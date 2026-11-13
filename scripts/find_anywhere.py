import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from app.models.class_report import ClassReport
from sqlalchemy import text

def find_anywhere():
    db = SessionLocal()
    try:
        report_id = "7d50d9a0-10b1-4657-b516-c142ca57c7c5"
        # Usando raw SQL para garantir que não há filtros de soft delete do ORM (se houver)
        sql = text("SELECT id, data_aula, estudio, start_time, end_time, status, is_deleted FROM class_reports WHERE id = :id")
        result = db.execute(sql, {"id": report_id}).fetchone()
        
        if result:
            print(f"\n--- Relatório Encontrado via SQL ---")
            print(result)
        else:
            print(f"ID {report_id} realmente não existe na tabela class_reports.")
            
            # Listar os 5 primeiros IDs para ver o formato
            print("\nExemplo de IDs na tabela:")
            sample = db.execute(text("SELECT id FROM class_reports LIMIT 5")).fetchall()
            for s in sample:
                print(s[0])
                
    finally:
        db.close()

if __name__ == "__main__":
    find_anywhere()
