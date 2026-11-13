"""
Compliance com verificação ATRASADA (fluxo: finaliza → Pendente → aguarda ~2,5h
→ verifica → Verde). Testa a config e o agendamento com atraso inicial.
"""

from app.core.config import get_settings
from app.tasks import worker


def test_config_compliance_tem_atraso_de_2_a_3h():
    s = get_settings()
    assert 2 * 3600 <= s.COMPLIANCE_INITIAL_DELAY_SECONDS <= 3 * 3600
    assert s.COMPLIANCE_RETRY_INTERVAL_SECONDS == 900   # 15 min
    assert s.COMPLIANCE_MAX_RETRIES >= 1


def test_agendar_verificacao_inicial_dispara_com_atraso(monkeypatch):
    capturado = {}

    def fake_apply_async(args=None, countdown=None, **kwargs):
        capturado["args"] = args
        capturado["countdown"] = countdown

    monkeypatch.setattr(worker.verificar_compliance_drive, "apply_async", fake_apply_async)

    worker.agendar_verificacao_inicial("rid-123", "ARQUIVO EXEMPLO.mp4")

    # NÃO checa na hora: usa o atraso inicial configurado
    assert capturado["countdown"] == get_settings().COMPLIANCE_INITIAL_DELAY_SECONDS
    assert capturado["args"] == ["rid-123", "ARQUIVO EXEMPLO.mp4"]
