import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# DATABASE_URL no .env pode estar como 'db', mas localmente pode ser 'localhost'
# Se falhar com 'db', tentaremos 'localhost'
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("DATABASE_URL não encontrada no .env")
    exit(1)

# Ajuste para rodar localmente se estiver apontando para o serviço docker 'db'
if "@db:" in db_url:
    db_url = db_url.replace("@db:", "@localhost:")

engine = create_engine(db_url)

queries = {
    "4": """
       SELECT 
         cr.horario_aula,
         cr.turno,
         cr.start_time,
         cr.end_time,
         t.nomenclatura_padrao as turma,
         cr.data_aula
       FROM class_reports cr
       JOIN turmas t ON t.id = cr.turma_id
       WHERE cr.is_deleted = false
         AND cr.status != 'CANCELADO'
         AND cr.start_time IS NOT NULL
         AND cr.turno = 'Manhã'
         AND cr.start_time >= '18:00:00'
       ORDER BY cr.data_aula DESC
       LIMIT 10;
    """,
    "5": """
       SELECT 
         cr.horario_aula,
         cr.turno,
         cr.start_time,
         cr.end_time,
         t.nomenclatura_padrao as turma,
         cr.data_aula
       FROM class_reports cr
       JOIN turmas t ON t.id = cr.turma_id
       WHERE cr.is_deleted = false
         AND cr.status != 'CANCELADO'
         AND cr.start_time IS NOT NULL
         AND cr.turno = 'Noite'
         AND cr.start_time < '12:00:00'
       ORDER BY cr.data_aula DESC
       LIMIT 10;
    """,
    "6_canal": """
       -- Choques de canal em estúdios diferentes
       SELECT COUNT(*) as choques_canal
       FROM class_reports a
       JOIN class_reports b ON (
         a.data_aula = b.data_aula AND
         a.id != b.id AND
         a.is_deleted = false AND
         b.is_deleted = false AND
         a.status != 'CANCELADO' AND
         b.status != 'CANCELADO' AND
         a.canal_utilizado = b.canal_utilizado AND
         a.estudio != b.estudio AND
         a.start_time IS NOT NULL AND
         b.start_time IS NOT NULL AND
         a.start_time < b.end_time AND
         a.end_time > b.start_time
       )
       WHERE a.data_aula >= CURRENT_DATE - INTERVAL '7 days';
    """,
    "6_estudio": """
       -- Choques de estúdio
       SELECT COUNT(*) as choques_estudio
       FROM class_reports a
       JOIN class_reports b ON (
         a.data_aula = b.data_aula AND
         a.id != b.id AND
         a.is_deleted = false AND
         b.is_deleted = false AND
         a.status != 'CANCELADO' AND
         b.status != 'CANCELADO' AND
         a.estudio = b.estudio AND
         a.start_time IS NOT NULL AND
         b.start_time IS NOT NULL AND
         a.start_time < b.end_time AND
         a.end_time > b.start_time
       )
       WHERE a.data_aula >= CURRENT_DATE - INTERVAL '7 days';
    """
}

with engine.connect() as conn:
    for name, query in queries.items():
        print(f"--- Query {name} ---")
        result = conn.execute(text(query))
        rows = result.fetchall()
        if not rows:
            print("Nenhum registro encontrado.")
        else:
            for row in rows:
                print(row)
        print("\n")
