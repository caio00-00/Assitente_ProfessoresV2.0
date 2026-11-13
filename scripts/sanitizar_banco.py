"""
Canal Educação v3.0 — Script de Sanitização de Professores Duplicados.

TASK 02: Sanitização e Unicidade de Professores.
Critério de unicidade: lower(nome_completo).
O ID menor (ou com mais relações) é o "Oficial".
Merge: Atualiza Grade, ClassReport (titular e substituto), ProfessorDisciplina.

Uso:
    docker compose exec web python scripts/sanitizar_banco.py
"""

import sys
import os

# Adiciona o diretório raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import SessionLocal
from app.models.auxiliares import Professor, ProfessorDisciplina, Grade
from app.models.class_report import ClassReport


def merge_duplicate_professors(db: Session) -> dict:
    """
    Identifica e mescla professores duplicados com base em lower(nome).
    
    Returns:
        dict com estatísticas da operação
    """
    stats = {
        "groups_found": 0,
        "duplicates_merged": 0,
        "grades_updated": 0,
        "reports_titular_updated": 0,
        "reports_substituto_updated": 0,
        "professor_disciplinas_updated": 0,
        "professor_disciplinas_removed": 0,
        "unknown_created": False,
    }

    try:
        # 1. Encontrar grupos de nomes duplicados (case-insensitive)
        duplicates = (
            db.query(
                func.lower(Professor.nome).label("nome_lower"),
                func.count(Professor.id).label("cnt"),
            )
            .group_by(func.lower(Professor.nome))
            .having(func.count(Professor.id) > 1)
            .all()
        )

        stats["groups_found"] = len(duplicates)
        print(f"\n📊 Encontrados {len(duplicates)} grupos de professores duplicados.\n")

        if not duplicates:
            print("✅ Nenhuma duplicata encontrada. Base já está limpa.")
            return stats

        for dup in duplicates:
            nome_lower = dup.nome_lower

            # Buscar todos os professores com este nome (case-insensitive)
            professors = (
                db.query(Professor)
                .filter(func.lower(Professor.nome) == nome_lower)
                .order_by(Professor.id)
                .all()
            )

            if len(professors) < 2:
                continue

            # Oficial: primeiro criado (menor ID) — geralmente tem mais relações
            oficial = professors[0]
            duplicados = professors[1:]

            print(f"  🔀 Grupo: '{oficial.nome}' — {len(duplicados)} duplicata(s)")

            for dup_prof in duplicados:
                dup_id = dup_prof.id

                # 2.a Atualizar Grade.professor_id
                grades_updated = (
                    db.query(Grade)
                    .filter(Grade.professor_id == dup_id)
                    .update({"professor_id": oficial.id}, synchronize_session="fetch")
                )
                stats["grades_updated"] += grades_updated

                # 2.b Atualizar ClassReport.professor_id (titular)
                reports_titular = (
                    db.query(ClassReport)
                    .filter(ClassReport.professor_id == dup_id)
                    .update({"professor_id": oficial.id}, synchronize_session="fetch")
                )
                stats["reports_titular_updated"] += reports_titular

                # 2.c Atualizar ClassReport.professor_substituto_id
                reports_sub = (
                    db.query(ClassReport)
                    .filter(ClassReport.professor_substituto_id == dup_id)
                    .update({"professor_substituto_id": oficial.id}, synchronize_session="fetch")
                )
                stats["reports_substituto_updated"] += reports_sub

                # 2.d Atualizar ProfessorDisciplina
                # Fazer via relacional para não dar erro de StaleData
                oficial_discs = {d.id for d in oficial.disciplinas}
                for d in dup_prof.disciplinas:
                    if d.id not in oficial_discs:
                        oficial.disciplinas.append(d)
                        oficial_discs.add(d.id)
                        stats["professor_disciplinas_updated"] += 1
                    else:
                        stats["professor_disciplinas_removed"] += 1
                
                # Limpa do dup_prof para que o SQLAlchemy possa deletar a entity em segurança
                dup_prof.disciplinas.clear()

                # 2.e Remover o professor duplicado
                db.delete(dup_prof)
                stats["duplicates_merged"] += 1
                print(f"    ✅ Duplicata {dup_id} mesclada em {oficial.id}")

        # 3. Garantir que existe um professor "Unknown" para relatórios órfãos
        unknown = db.query(Professor).filter(Professor.nome == "Unknown").first()
        if not unknown:
            unknown = Professor(nome="Unknown")
            db.add(unknown)
            stats["unknown_created"] = True
            print("\n  📌 Professor 'Unknown' criado para relatórios órfãos.")

        # 4. Commit atômico
        db.commit()
        print(f"\n✅ Sanitização concluída com sucesso!")
        print(f"   Grupos processados: {stats['groups_found']}")
        print(f"   Duplicatas mescladas: {stats['duplicates_merged']}")
        print(f"   Grades atualizadas: {stats['grades_updated']}")
        print(f"   Relatórios (titular): {stats['reports_titular_updated']}")
        print(f"   Relatórios (substituto): {stats['reports_substituto_updated']}")
        print(f"   Prof-Disciplinas migradas: {stats['professor_disciplinas_updated']}")
        print(f"   Prof-Disciplinas removidas: {stats['professor_disciplinas_removed']}")

        return stats

    except Exception as e:
        print(f"\n❌ ERRO na sanitização: {str(e)}")
        print("   ⚠️ Revertendo todas as alterações (rollback)...")
        db.rollback()
        raise


if __name__ == "__main__":
    print("=" * 60)
    print("  Canal Educação — Sanitização de Professores Duplicados")
    print("=" * 60)

    db = SessionLocal()
    try:
        merge_duplicate_professors(db)
    finally:
        db.close()
