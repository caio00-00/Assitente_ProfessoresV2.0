import sys
sys.path.append("/app")
from app.core.database import SessionLocal
from sqlalchemy import text

def run_diagnostics():
    db = SessionLocal()
    try:
        # 4. Exemplo real de relatórios (preenchido vs nulo)
        print("\n=== QUERY 4: EXEMPLOS DE RELATÓRIOS ===")
        q4 = text("""
            SELECT
                id,
                turma_id,
                horario_aula,
                turno,
                start_time,
                end_time,
                created_at
            FROM class_reports
            WHERE is_deleted = false
            ORDER BY start_time NULLS FIRST
            LIMIT 6;
        """)
        res4 = db.execute(q4).fetchall()
        for row in res4:
            print(f"ID: {row[0]} | Turma: {row[1]} | Horário Aula: {row[2]:<15} | Turno: {row[3]:<10} | Início: {row[4]} | Fim: {row[5]} | Criado em: {row[6]}")

        # 5. Nomenclatura das Turmas
        print("\n=== QUERY 5: NOMENCLATURA DAS TURMAS ===")
        q5 = text("""
            SELECT
                id,
                nome,
                serie_modulo,
                turno,
                nomenclatura_padrao
            FROM turmas
            LIMIT 10;
        """)
        res5 = db.execute(q5).fetchall()
        for row in res5:
            print(f"ID: {row[0]} | Nome: {row[1]:<25} | Série: {row[2]:<10} | Turno: {row[3]:<10} | Padrao: {row[4]}")

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_diagnostics()
