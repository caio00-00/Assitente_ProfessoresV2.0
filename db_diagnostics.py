import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def run_diagnostics():
    db = SessionLocal()
    try:
        # 1. Mapeamento por turno
        print("\n=== QUERY 1: MAPEAMENTO POR TURNO ===")
        q1 = text("""
            SELECT
                turno,
                horario_aula,
                start_time,
                end_time,
                COUNT(*) as total_registros
            FROM class_reports
            WHERE is_deleted = false
                AND start_time IS NOT NULL
                AND end_time IS NOT NULL
                AND turno IS NOT NULL
            GROUP BY turno, horario_aula, start_time, end_time
            ORDER BY turno, start_time;
        """)
        res1 = db.execute(q1).fetchall()
        for row in res1:
            print(f"Turno: {row[0]:<10} | Horário: {row[1]:<15} | Início: {row[2]} | Fim: {row[3]} | Total: {row[4]}")

        # 2. Registros sem horário
        print("\n=== QUERY 2: REGISTROS SEM HORÁRIO ===")
        q2 = text("""
            SELECT
                turno,
                horario_aula,
                COUNT(*) as total_sem_horario
            FROM class_reports
            WHERE is_deleted = false
                AND (start_time IS NULL OR end_time IS NULL)
            GROUP BY turno, horario_aula
            ORDER BY turno, horario_aula;
        """)
        res2 = db.execute(q2).fetchall()
        for row in res2:
            print(f"Turno: {row[0]:<10} | Horário: {row[1]:<15} | Total Sem Horário: {row[2]}")

        # 3. Lista de tabelas
        print("\n=== QUERY 3: LISTA DE TABELAS ===")
        q3 = text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        res3 = db.execute(q3).fetchall()
        for row in res3:
            print(f"Tabela: {row[0]}")

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_diagnostics()
