import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def run_diagnostics():
    db = SessionLocal()
    try:
        # 4. Verificar campos de controle de tentativas
        print("\n=== QUERY 4: CAMPOS DE CONTROLE DE RETRY ===")
        q4 = text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'class_reports'
              AND column_name ILIKE ANY(ARRAY[
                '%tentativa%', '%retry%', '%attempt%',
                '%sync%', '%compliance%', '%pending%'
              ]);
        """)
        res4 = db.execute(q4).fetchall()
        for row in res4:
            print(f"Coluna: {row[0]:<25} | Tipo: {row[1]}")

        # 5. Estatísticas de status_compliance
        print("\n=== QUERY 5: ESTATÍSTICAS DE COMPLIANCE ===")
        q5 = text("""
            SELECT
                status_compliance,
                COUNT(*) as total,
                MIN(created_at) as mais_antigo,
                MAX(created_at) as mais_recente
            FROM class_reports
            WHERE is_deleted = false
            GROUP BY status_compliance
            ORDER BY total DESC;
        """)
        res5 = db.execute(q5).fetchall()
        for row in res5:
            print(f"Status: {str(row[0]):<12} | Total: {row[1]:<5} | Antigo: {row[2]} | Recente: {row[3]}")

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_diagnostics()
