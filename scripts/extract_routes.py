import re

with open("app/api/rotas_report.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.strip().startswith("@router."):
        # get the next line for function name
        func_name = lines[i+1].strip() if i+1 < len(lines) else ""
        print(f"L{i+1}: {line.strip()}")
        print(f"      {func_name}")
