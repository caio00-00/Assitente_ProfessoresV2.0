"""
Regra única do status de compliance (Drive) do relatório de aula.

Verde = tem vídeo NO DRIVE (video_link) E PDF/slide no Drive (slide_link).
O link do Vimeo não conta. Enquanto faltar algum, o
status de busca (Pendente/Vermelho) continua valendo. Antes a regra estava
espalhada: links gravados depois (ex.: vínculo do Vimeo com drive_url, ou
relatórios que já tinham virado Vermelho) nunca voltavam para Verde.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.class_report import ClassReport


def tem_video(report) -> bool:
    return bool(getattr(report, "video_link", None))


def tem_slide(report) -> bool:
    return bool(getattr(report, "slide_link", None))


def compliance_completo(report) -> bool:
    return tem_video(report) and tem_slide(report)


def aplicar_verde_se_completo(report) -> bool:
    """Marca Verde quando o relatório já tem vídeo e PDF. Retorna True se mudou."""
    if compliance_completo(report) and report.status_compliance != "Verde":
        report.status_compliance = "Verde"
        return True
    return False


def corrigir_verdes_pendentes(db: Session) -> int:
    """
    Corrige em lote relatórios que já têm vídeo e PDF no Drive mas ainda
    não estão Verde. Idempotente — pode rodar a qualquer momento.
    """
    total = (
        db.query(ClassReport)
        .filter(
            ClassReport.is_deleted == False,  # noqa: E712
            ClassReport.status_compliance != "Verde",
            ClassReport.slide_link.isnot(None),
            ClassReport.slide_link != "",
            ClassReport.video_link.isnot(None),
            ClassReport.video_link != "",
        )
        .update({"status_compliance": "Verde"}, synchronize_session=False)
    )
    db.commit()
    return total
