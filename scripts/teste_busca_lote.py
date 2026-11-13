"""
Teste em lote — Busca de links no Google Drive.
Lê nomes de data/teste_busca_linksdrive.txt e busca vídeo + slide para cada um.
"""
import sys
import os
import json
import time

# Adiciona raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.sync_drive import buscar_video_no_drive, buscar_slide_no_drive

INPUT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "teste_busca_linksdrive.txt"
)
OUTPUT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "resultado_busca_lote.json"
)

INTEGRITY_THRESHOLD = 104857600  # 100 MB em bytes


def main():
    # Ler nomes do arquivo
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        nomes = [
            line.strip() for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    print(f"\n{'='*70}")
    print(f"  TESTE EM LOTE — BUSCA DE LINKS NO GOOGLE DRIVE")
    print(f"  Total de nomes a buscar: {len(nomes)}")
    print(f"{'='*70}\n")

    resultados = []
    videos_ok = 0
    slides_ok = 0
    videos_corrompidos = 0

    for i, nome in enumerate(nomes, 1):
        print(f"\n--- [{i}/{len(nomes)}] {nome}")

        # --- Busca Vídeo ---
        try:
            video = buscar_video_no_drive(nome)
        except Exception as e:
            print(f"  ❌ Erro na busca de vídeo: {e}")
            video = None

        video_result = {
            "encontrado": False,
            "nome_drive": None,
            "link": None,
            "tamanho_mb": None,
            "integridade": "N/A"
        }

        if video:
            size_bytes = int(video.get("size", 0))
            size_mb = round(size_bytes / (1024 * 1024), 2)
            integridade = "Íntegro (>100MB)" if size_bytes >= INTEGRITY_THRESHOLD else "Corrompido (<100MB)"
            video_result = {
                "encontrado": True,
                "nome_drive": video.get("name"),
                "link": video.get("webViewLink"),
                "tamanho_mb": size_mb,
                "integridade": integridade
            }
            videos_ok += 1
            if size_bytes < INTEGRITY_THRESHOLD:
                videos_corrompidos += 1

        # --- Busca Slide ---
        try:
            slide = buscar_slide_no_drive(nome)
        except Exception as e:
            print(f"  ❌ Erro na busca de slide: {e}")
            slide = None

        slide_result = {
            "encontrado": False,
            "nome_drive": None,
            "link": None,
            "formato": None
        }

        if slide:
            slide_name = slide.get("name", "")
            fmt = None
            if slide_name.lower().endswith(".pdf"):
                fmt = "pdf"
            elif slide_name.lower().endswith(".pptx"):
                fmt = "pptx"
            slide_result = {
                "encontrado": True,
                "nome_drive": slide_name,
                "link": slide.get("webViewLink"),
                "formato": fmt
            }
            slides_ok += 1

        resultados.append({
            "nome_buscado": nome,
            "video": video_result,
            "slide": slide_result
        })

        # Pequeno delay para evitar rate limits
        time.sleep(0.3)

    total = len(nomes)
    videos_nao = total - videos_ok
    slides_nao = total - slides_ok

    taxa_video = f"{videos_ok}/{total} — {round(videos_ok/total*100) if total else 0}%"
    taxa_slide = f"{slides_ok}/{total} — {round(slides_ok/total*100) if total else 0}%"

    output = {
        "resultados": resultados,
        "resumo": {
            "total_nomes": total,
            "videos_encontrados": videos_ok,
            "slides_encontrados": slides_ok,
            "videos_nao_encontrados": videos_nao,
            "slides_nao_encontrados": slides_nao,
            "videos_corrompidos": videos_corrompidos,
            "taxa_sucesso_video": taxa_video,
            "taxa_sucesso_slide": taxa_slide
        }
    }

    # Salvar JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Imprimir resultado
    print(f"\n\n{'='*70}")
    print(f"  RESULTADO FINAL")
    print(f"{'='*70}")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n{'='*70}")
    print(f"  RESUMO")
    print(f"{'='*70}")
    print(f"  Total de nomes buscados:    {total}")
    print(f"  Vídeos encontrados:         {videos_ok}")
    print(f"  Vídeos NÃO encontrados:     {videos_nao}")
    print(f"  Vídeos corrompidos (<100MB): {videos_corrompidos}")
    print(f"  Slides encontrados:         {slides_ok}")
    print(f"  Slides NÃO encontrados:     {slides_nao}")
    print(f"  Taxa de sucesso (vídeo):    {taxa_video}")
    print(f"  Taxa de sucesso (slide):    {taxa_slide}")
    print(f"{'='*70}")
    print(f"  JSON salvo em: {OUTPUT_FILE}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
