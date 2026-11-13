"""
Ponto de entrada para a Vercel (ela procura `app` num index.py na raiz).

No Docker nada usa este arquivo: lá a API sobe com `app.main:app`.
"""
from app.main import app  # noqa: F401
