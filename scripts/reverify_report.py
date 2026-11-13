from app.tasks.worker import verificar_compliance_drive
from app.core.database import SessionLocal
from app.models.class_report import ClassReport
import sys

def manually_run_sync(report_id):
    db = SessionLocal()
    report = db.query(ClassReport).filter(ClassReport.id == report_id).first()
    if not report:
        print(f"Relatório {report_id} não encontrado.")
        return
    
    nome = report.nome_ficheiro_gerado
    print(f"Re-executando sincronização para: {nome}")
    
    # Chama o método .run para ignorar a lógica de 'self' do Celery se necessário, 
    # ou apenas passa os argumentos se chamarmos a função original.
    # Como está decorada, verificar_compliance_drive é um objeto Task.
    
    from app.services.sync_drive import buscar_video_no_drive, buscar_slide_no_drive
    
    # Simula a lógica do worker manualmente para garantir que vemos o output
    print(f"🔍 Buscando vídeo: {nome}")
    video = buscar_video_no_drive(nome)
    if video:
        print(f"✅ Vídeo: {video.get('webViewLink')}")
        report.video_link = video.get('webViewLink')
        report.status_compliance = "Verde"
    
    print(f"🔍 Buscando slide para: {nome}")
    slide = buscar_slide_no_drive(nome)
    if slide:
        print(f"✅ Slide encontrado: {slide.get('name')} -> {slide.get('webViewLink')}")
        report.slide_link = slide.get('webViewLink')
    else:
        print(f"⚠️ Slide não encontrado.")
        
    db.commit()
    db.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        manually_run_sync(sys.argv[1])
    else:
        # ID do usuário
        manually_run_sync('cd9da946-7cc7-4114-bb6f-6e2949eb0515')
