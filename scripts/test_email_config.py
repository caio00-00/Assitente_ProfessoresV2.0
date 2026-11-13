#!/usr/bin/env python3
"""
Diagnóstico de configuração SMTP (sem expor senha).
Uso:
  python scripts/test_email_config.py
  python scripts/test_email_config.py --send seu@email.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.email_service import get_email_config_status, send_invite_email_sync


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico de email transacional")
    parser.add_argument(
        "--send",
        metavar="EMAIL",
        help="Envia email de teste de convite para o endereço informado",
    )
    args = parser.parse_args()

    status = get_email_config_status()
    print("=== Configuração de Email ===")
    for key, value in status.items():
        print(f"{key}: {value}")

    missing = []
    if not status["smtp_user_configured"]:
        missing.append("SMTP_USER")
    if not status["smtp_password_configured"]:
        missing.append("SMTP_PASSWORD")
    if missing:
        print("\n⚠️  Variáveis ausentes no .env:", ", ".join(missing))
        print("   Sem elas, o sistema apenas registra o link no log.")
        return 1

    if not args.send:
        print("\nOK: credenciais presentes. Use --send email@dominio.com para testar envio real.")
        return 0

    print(f"\nEnviando email de teste para {args.send}...")
    send_invite_email_sync(args.send, "Usuário Teste", "token-diagnostico")
    print("✅ Comando de envio concluído. Verifique a caixa de entrada e os logs da API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
