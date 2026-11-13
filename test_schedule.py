import sys
sys.path.append("/app")
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.api.rotas_report import criar_relatorio, editar_relatorio
from app.schemas.class_report import ClassReportCreate
from app.models.user import User
from app.models.turma import Turma
from app.models.auxiliares import Disciplina, Professor
from app.models.class_report import ClassReport
from datetime import date
from fastapi import HTTPException
import uuid

def run_tests():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.is_active == True).first()
        if not user:
            print("Nenhum usuário ativo encontrado.")
            return

        turma = db.query(Turma).filter(Turma.nomenclatura_padrao.like('%NOITE%'), Turma.nomenclatura_padrao.notilike('%EJA%')).first()
        disciplina = db.query(Disciplina).first()
        professor = db.query(Professor).first()

        if not turma or not disciplina or not professor:
            print("Faltam dados básicos.")
            return

        print(f"Turma selecionada: {turma.nome} (Padrão: {turma.nomenclatura_padrao})")
        
        base_data = {
            "turma_id": turma.id,
            "disciplina_id": disciplina.id,
            "professor_id": professor.id,
            "data_aula": date(2026, 12, 1),
            "estudio": "Estúdio 01",
            "regular": "Sim",
            "status": "RASCUNHO",
            "turno": "Noite",
            "tipo_aula": "Gravação estúdio",
            "canal_utilizado": "Canal SEDUC PI 1",
            "conteudo_ministrado": "Teste 123",
            "tipo_recursos_utilizados": [],
            "youtube_link": "http://youtube.com",
            "bncc_habilidades": "",
            "interacao_professor_aluno": "Não",
            "atividade_pratica": "Nenhuma",
            "problema_material": "Não",
            "teve_substituicao": False,
            "teve_atraso": False
        }

        # Teste A: Criar relatório
        print("\n--- TESTE A: Criação de Relatório (1º Horário) ---")
        data = ClassReportCreate(**base_data, horario_aula="1º Horário")
        
        try:
            report1 = criar_relatorio(data=data, bypass_clash=False, db=db, current_user=user)
            print(f"Relatório 1 criado com sucesso! ID: {report1.id}")
            print(f"start_time: {report1.start_time}, end_time: {report1.end_time}")
            if str(report1.start_time) == "18:30:00" and str(report1.end_time) == "19:15:00":
                print("-> Teste A: PASSOU")
            else:
                print("-> Teste A: FALHOU")
        except HTTPException as e:
            print(f"Erro ao criar relatório 1: {e.detail}")
            return
            
        # Teste B: Criar segundo relatório (Choque)
        print("\n--- TESTE B: Criação do 2º Relatório (Mesmo horário/estúdio) ---")
        data2 = ClassReportCreate(**base_data, horario_aula="1º Horário")
        
        try:
            report2 = criar_relatorio(data=data2, bypass_clash=False, db=db, current_user=user)
            print(f"Relatório 2 criado com sucesso? ID: {report2.id}")
            print("-> Teste B: FALHOU (Deveria dar erro 409)")
        except HTTPException as e:
            print(f"HTTPException lançada: {e.status_code} - {e.detail}")
            if e.status_code == 400 or e.status_code == 409:
                print("-> Teste B: PASSOU")
            else:
                print("-> Teste B: FALHOU (Código inesperado)")

        # Teste C: Edição verificando choque
        print("\n--- TESTE C: Edição de Relatório Verificando Choque ---")
        data3 = ClassReportCreate(**base_data, horario_aula="2º Horário")
        report3 = criar_relatorio(data=data3, bypass_clash=False, db=db, current_user=user)
        print(f"Relatório 3 criado no 2º Horário. ID: {report3.id}")
        
        data_edit = ClassReportCreate(**base_data, horario_aula="1º Horário")
        try:
            report_edit = editar_relatorio(report_id=report3.id, data=data_edit, db=db, current_user=user)
            print("-> Teste C: FALHOU (Deveria dar erro)")
        except HTTPException as e:
            print(f"HTTPException lançada: {e.status_code} - {e.detail}")
            if e.status_code == 409:
                print("-> Teste C: PASSOU")
            else:
                print("-> Teste C: FALHOU (Código inesperado)")

        # Cleanup
        print("\nLimpando registros de teste...")
        db.query(ClassReport).filter(ClassReport.id.in_([report1.id, report3.id])).delete(synchronize_session=False)
        db.commit()

    except Exception as e:
        print(f"Erro geral: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
