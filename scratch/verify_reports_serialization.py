from app.core.database import SessionLocal
from app.models.class_report import ClassReport
from app.schemas.class_report import ClassReportResponse

db = SessionLocal()
reports = db.query(ClassReport).all()
print(f"Testing {len(reports)} reports...")
errors = 0
for r in reports:
    try:
        ClassReportResponse.model_validate(r)
    except Exception as e:
        print(f"Error in report {r.id}: {e}")
        errors += 1
print(f"Finished. Total errors: {errors}")
db.close()
