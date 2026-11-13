"""Test cases for naming engine P1 bug."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.naming_engine import gerar_nome_padronizado, verificar_sufixo_geminada
from datetime import date

print("=== gerar_nome_padronizado ===")
cases = [
    "Tema P1",
    "Tema - P1", 
    "Tema_P1",
    "Tema P1.mp4",
    "TemaP1",
    "Equacoes do 2o grau P1",
    "Equacoes do 2o grau P2",
    "Equacoes do 2o grau NP",
    "Aula sobre HTML5 e CSS3 P1",
    "Exercicio comp4",
]

for c in cases:
    result = gerar_nome_padronizado("EM 1A MH", "MAT", date(2025, 4, 22), c)
    has_suffix = any(result.endswith(f"{s}.mp4") for s in ["P1", "P2", "P3", "NP"])
    flag = "OK" if ("P1" in c and "P1" in result) or ("P2" in c and "P2" in result) or ("NP" in c and "NP" in result) or not any(s in c for s in ["P1", "P2", "NP"]) else "BUG"
    print(f"  [{flag}] Input: {c:35s} -> {result}")

print()
print("=== verificar_sufixo_geminada ===")
tests = [
    ("Tema P1", True),
    ("Tema P2", True),
    ("Tema P3", True),
    ("Tema NP", True),
    ("TemaP1", True),
    ("Tema p1", True),
    ("Tema", False),
    ("Tema P4", False),
    ("Tema P1 extra", False),
]

for text, expected in tests:
    result = verificar_sufixo_geminada(text)
    flag = "OK" if result == expected else "BUG"
    print(f"  [{flag}] {text:20s} -> {result} (esperado: {expected})")
