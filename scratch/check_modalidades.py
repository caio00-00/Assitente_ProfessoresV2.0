import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.models.turma import Turma
from sqlalchemy import func

db = SessionLocal()

print("--- MODALIDADES IN DATABASE ---")
results = db.query(Turma.modalidade, func.count(Turma.id)).group_by(Turma.modalidade).all()
for mod, count in results:
    print(f"Modalidade: '{mod}' | Count: {count}")

db.close()
