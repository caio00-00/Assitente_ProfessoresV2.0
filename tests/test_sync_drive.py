"""
AP-004 — Busca de PDF e MP4 no Drive por MIME Type exato.

Critérios de aceitação:
  - Vídeo: qualquer arquivo do tipo vídeo (mimeType contains 'video/') — reunião out/2026:
    vale o tipo do arquivo, não a extensão .mp4 no nome
  - Slide: mimeType = 'application/pdf'
  - Fallback consistente: mantém o mesmo filtro de MIME da query exata
  - Sem mistura de extensões (vídeo não procura .pdf/.pptx e vice-versa)

Os testes interceptam a query enviada ao Drive (campo `q` de files().list)
para verificar o filtro, sem chamar a API real.
"""

import app.services.sync_drive as sd


class _FakeFilesResource:
    def __init__(self, recorder, results):
        self._recorder = recorder
        self._results = results
        self._last = None

    def list(self, **kwargs):
        self._recorder.append(kwargs.get("q", ""))
        # próxima resposta da fila (ou vazio)
        self._last = self._results.pop(0) if self._results else {"files": []}
        return self

    def execute(self):
        return self._last


class _FakeDriveService:
    def __init__(self, recorder, results):
        self._files = _FakeFilesResource(recorder, results)

    def files(self):
        return self._files


def _patch_service(monkeypatch, queries, results):
    fake = _FakeDriveService(queries, results)
    monkeypatch.setattr(sd, "get_drive_service", lambda: fake)
    return fake


# ─── Vídeo (MP4) ──────────────────────────────────────────────────────

def test_busca_video_filtra_pelo_tipo_video(monkeypatch):
    queries = []
    _patch_service(monkeypatch, queries, [{"files": [{"id": "1", "name": "AULA 01.mov", "mimeType": "video/quicktime"}]}])

    f = sd.buscar_video_no_drive("AULA 01.mp4")

    assert "mimeType contains 'video/'" in queries[0]
    assert ".mp4" not in queries[0]          # a extensão do nome não entra na busca
    assert f and f["name"] == "AULA 01.mov"


def test_busca_video_fallback_mantem_tipo_video(monkeypatch):
    queries = []
    # 1ª query exata → vazio; 2ª (fallback) → encontra
    _patch_service(
        monkeypatch,
        queries,
        [{"files": []}, {"files": [{"id": "1", "name": "AULA 01.mp4"}]}],
    )

    sd.buscar_video_no_drive("AULA 01")

    assert len(queries) == 2, "deveria cair no fallback"
    assert "mimeType contains 'video/'" in queries[1]
    # não mistura extensões de slide na normalização do alvo
    assert ".pdf" not in queries[1] and ".pptx" not in queries[1]


# ─── Slide (PDF) ──────────────────────────────────────────────────────

def test_busca_slide_filtra_application_pdf(monkeypatch):
    queries = []
    _patch_service(monkeypatch, queries, [{"files": [{"id": "1", "name": "AULA 01.pdf"}]}])

    sd.buscar_slide_no_drive("AULA 01")

    assert "mimeType = 'application/pdf'" in queries[0]


def test_busca_slide_fallback_mantem_application_pdf(monkeypatch):
    queries = []
    _patch_service(
        monkeypatch,
        queries,
        [{"files": []}, {"files": [{"id": "1", "name": "AULA 01.pdf"}]}],
    )

    sd.buscar_slide_no_drive("AULA 01")

    assert len(queries) == 2, "deveria cair no fallback"
    assert "mimeType = 'application/pdf'" in queries[1]
