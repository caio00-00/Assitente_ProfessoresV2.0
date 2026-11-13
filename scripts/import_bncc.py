import csv
import json
import os
import sys

# Adiciona o diretório raiz ao path para imports locais
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def import_bncc():
    """
    ETL principal de habilidades BNCC.
    1. Lê o CSV original (bncc_total.csv) com encoding correto (utf-8-sig).
    2. Importa as habilidades de Computação do arquivo .txt diagramado.
    3. Faz merge e deduplicação por código.
    4. Grava o JSON final em app/data/bncc.json.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(base_dir, "bncc_total.csv")
    txt_path = os.path.join(base_dir, "bncccomputacaocompletodiagramado.txt")
    json_dir = os.path.join(base_dir, "app", "data")
    json_path = os.path.join(json_dir, "bncc.json")

    if not os.path.exists(json_dir):
        os.makedirs(json_dir)

    # ── 1. Importar habilidades do CSV ──────────────────────────────────
    bncc_data = []

    if not os.path.exists(csv_path):
        print(f"[WARN] Arquivo CSV nao encontrado: {csv_path}")
    else:
        try:
            # utf-8-sig trata o BOM (Byte Order Mark) automaticamente
            with open(csv_path, mode='r', encoding='utf-8-sig') as csvfile:
                reader = csv.reader(csvfile)
                header = next(reader, None)  # Pula o cabeçalho (codigo,descricao)

                for row in reader:
                    if len(row) >= 2:
                        codigo = row[0].strip()
                        descricao = row[1].strip()
                        if codigo and descricao:
                            bncc_data.append({
                                "codigo": codigo,
                                "descricao": descricao,
                                "label": f"({codigo}) - {descricao}"
                            })
            print(f"[OK] CSV: {len(bncc_data)} habilidades carregadas")
        except Exception as e:
            print(f"[ERRO] Erro ao ler CSV: {e}")
            return

    # ── 2. Importar habilidades de Computação do TXT ────────────────────
    computacao_data = []
    if os.path.exists(txt_path):
        try:
            from scripts.parse_bncc_computacao import parse_bncc_computacao
            computacao_data = parse_bncc_computacao(txt_path)
            print(f"[OK] Computacao: {len(computacao_data)} habilidades extraidas")
        except Exception as e:
            print(f"[WARN] Erro ao parsear BNCC Computacao: {e}")
    else:
        print(f"[WARN] Arquivo de Computacao nao encontrado: {txt_path}")

    # ── 3. Merge e deduplicação por código ──────────────────────────────
    codigos_existentes = {item["codigo"] for item in bncc_data}
    novos = 0
    for item in computacao_data:
        if item["codigo"] not in codigos_existentes:
            bncc_data.append(item)
            codigos_existentes.add(item["codigo"])
            novos += 1

    if novos > 0:
        print(f"[OK] Merge: {novos} habilidades de Computacao adicionadas")

    # ── 4. Gravar JSON final ────────────────────────────────────────────
    try:
        with open(json_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(bncc_data, jsonfile, ensure_ascii=False, indent=2)
        print(f"[OK] Total: {len(bncc_data)} habilidades gravadas em {json_path}")
    except Exception as e:
        print(f"[ERRO] Erro ao gravar JSON: {e}")


if __name__ == "__main__":
    import_bncc()

