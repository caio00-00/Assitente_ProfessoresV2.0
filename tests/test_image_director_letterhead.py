"""Timbrado deve aparecer em todas as páginas do PDF (não só na primeira)."""
import io

from pypdf import PdfReader
from xhtml2pdf import pisa

from app.services.image_director_pdf import _apply_letterhead, _letterhead_page_pdf


def _sample_pdf_bytes(pages: int = 3) -> bytes:
    parts = []
    for i in range(1, pages + 1):
        if i > 1:
            parts.append('<div style="page-break-before: always"></div>')
        parts.append(f"<h1>Página {i}</h1><p>Conteúdo da página {i}.</p>")
    html = f"""<!DOCTYPE html><html><head><style>
    @page {{ size: A4; margin: 6.5cm 2cm 5.5cm 2cm; }}
    body {{ font-family: Helvetica; font-size: 10pt; }}
    </style></head><body>{''.join(parts)}</body></html>"""
    out = io.BytesIO()
    result = pisa.CreatePDF(html, dest=out, encoding="utf-8")
    assert not result.err
    return out.getvalue()


def test_letterhead_page_is_generated():
    pdf = _letterhead_page_pdf()
    assert pdf is not None
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 1


def test_letterhead_applied_to_all_pages():
    raw = _sample_pdf_bytes(pages=3)
    raw_reader = PdfReader(io.BytesIO(raw))
    assert len(raw_reader.pages) == 3

    stamped = _apply_letterhead(raw)
    stamped_reader = PdfReader(io.BytesIO(stamped))
    assert len(stamped_reader.pages) == 3
    assert len(stamped) > len(raw)
