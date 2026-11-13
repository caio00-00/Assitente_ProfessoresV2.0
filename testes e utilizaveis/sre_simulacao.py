import os
import sys

# Change working directory so imports work
os.chdir(r"c:\Users\Paulo\OROS\ce_assistente_professores (12)\ce_assistente_professores")
sys.path.append(os.getcwd())

import uuid
from datetime import date
from unittest.mock import patch
from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.models.class_report import ClassReport
from app.tasks.worker import verificar_compliance_drive

def run_simulation():
    db = SessionLocal()
    
    # Clean up previous test
    db.execute(text("DELETE FROM class_reports WHERE observacoes LIKE '%Falha de Integridade: Arquivo Corrompido ou Incompleto (Menos de 100MB)%'"))
    db.commit()

    user_id = db.execute(text("SELECT id FROM users LIMIT 1")).scalar()
    turma_id = db.execute(text("SELECT id FROM turmas LIMIT 1")).scalar()
    disc_id = db.execute(text("SELECT id FROM disciplinas LIMIT 1")).scalar()
    prof_id = db.execute(text("SELECT id FROM professores LIMIT 1")).scalar()
    
    report_id = uuid.uuid4()
    report_id_2 = uuid.uuid4()

    # Criar 2 relatorios: um para < 100MB e outro para > 100MB
    r1 = ClassReport(
        id=report_id,
        created_by=user_id,
        data_aula=date.today(),
        turno="Manhã",
        estudio="Estúdio 01",
        turma_id=turma_id,
        disciplina_id=disc_id,
        professor_id=prof_id,
        horario_aula="08:00",
        tipo_aula="Normal",
        canal_utilizado="Youtube",
        conteudo_ministrado="Teste 1",
        status="FINALIZADO",
        nome_ficheiro_gerado="video_curto.mp4"
    )
    r2 = ClassReport(
        id=report_id_2,
        created_by=user_id,
        data_aula=date.today(),
        turno="Manhã",
        estudio="Estúdio 01",
        turma_id=turma_id,
        disciplina_id=disc_id,
        professor_id=prof_id,
        horario_aula="09:00",
        tipo_aula="Normal",
        canal_utilizado="Youtube",
        conteudo_ministrado="Teste 2",
        status="FINALIZADO",
        nome_ficheiro_gerado="video_longo.mp4"
    )
    
    db.add(r1)
    db.add(r2)
    db.commit()

    print("--- SIMULAÇÃO 1: VÍDEO CURTO (45MB) ---")
    mock_file_curto = {
        'id': '123_curto',
        'name': 'video_curto.mp4',
        'webViewLink': 'http://drive/curto',
        'size': '47185920', # 45MB
        'md5Checksum': 'aaaabbbbccccdddd'
    }

    with patch('app.tasks.worker.buscar_video_no_drive', return_value=mock_file_curto):
        try:
            verificar_compliance_drive(str(report_id), "video_curto.mp4")
        except Exception as e:
            pass

    db.refresh(r1)
    print(f"Status Final: {r1.status_compliance}")
    print(f"Observacoes: {r1.observacoes}")

    print("\n--- SIMULAÇÃO 2: VÍDEO VÁLIDO (120MB) ---")
    mock_file_longo = {
        'id': '123_longo',
        'name': 'video_longo.mp4',
        'webViewLink': 'http://drive/longo',
        'size': '125829120', # 120MB
        'md5Checksum': '1234567890abcdef'
    }

    with patch('app.tasks.worker.buscar_video_no_drive', return_value=mock_file_longo):
        try:
            verificar_compliance_drive(str(report_id_2), "video_longo.mp4")
        except Exception as e:
            pass

    db.refresh(r2)
    print(f"Status Final: {r2.status_compliance}")
    print(f"MD5 Gravado: {r2.md5_checksum}")

    # Cleanup
    db.delete(r1)
    db.delete(r2)
    db.commit()
    db.close()

if __name__ == "__main__":
    run_simulation()
