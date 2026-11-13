"""
Busca rápida — mp4 + pdf para lista de nomes.
Usa query exata (name = '...') conforme sync_drive.py refatorado.
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.sync_drive import buscar_video_no_drive, buscar_slide_no_drive

INPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "busca_rapida.txt")
OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "resultado_busca_rapida.json")
INTEGRITY = 104857600

def main():
    with open(INPUT, "r", encoding="utf-8") as f:
        nomes = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]

    print(f"\n{'='*70}")
    print(f"  BUSCA RÁPIDA — {len(nomes)} nomes (query exata)")
    print(f"{'='*70}\n")

    resultados = []
    v_ok = s_ok = v_corr = 0

    for i, nome in enumerate(nomes, 1):
        print(f"\n--- [{i}/{len(nomes)}] {nome}")

        # Video
        try:
            video = buscar_video_no_drive(nome)
        except Exception as e:
            print(f"  ❌ Erro vídeo: {e}"); video = None

        vr = {"encontrado": False, "nome_drive": None, "link": None, "tamanho_mb": None, "integridade": "N/A"}
        if video:
            sz = int(video.get("size", 0))
            vr = {
                "encontrado": True,
                "nome_drive": video.get("name"),
                "link": video.get("webViewLink"),
                "tamanho_mb": round(sz / 1048576, 2),
                "integridade": "Íntegro (>100MB)" if sz >= INTEGRITY else "Corrompido (<100MB)"
            }
            v_ok += 1
            if sz < INTEGRITY: v_corr += 1

        # Slide
        try:
            slide = buscar_slide_no_drive(nome)
        except Exception as e:
            print(f"  ❌ Erro slide: {e}"); slide = None

        sr = {"encontrado": False, "nome_drive": None, "link": None, "formato": None}
        if slide:
            sn = slide.get("name", "")
            sr = {
                "encontrado": True,
                "nome_drive": sn,
                "link": slide.get("webViewLink"),
                "formato": "pdf" if sn.lower().endswith(".pdf") else "pptx" if sn.lower().endswith(".pptx") else None
            }
            s_ok += 1

        resultados.append({"nome_buscado": nome, "video": vr, "slide": sr})
        time.sleep(0.2)

    total = len(nomes)
    output = {
        "resultados": resultados,
        "resumo": {
            "total": total,
            "videos_encontrados": v_ok, "slides_encontrados": s_ok,
            "videos_nao": total - v_ok, "slides_nao": total - s_ok,
            "videos_corrompidos": v_corr,
            "taxa_video": f"{v_ok}/{total} — {round(v_ok/total*100)}%",
            "taxa_slide": f"{s_ok}/{total} — {round(s_ok/total*100)}%"
        }
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"{'='*70}")
    print(f"  Vídeos: {v_ok}/{total}  |  Slides: {s_ok}/{total}  |  Corrompidos: {v_corr}")
    print(f"  Salvo em: {OUTPUT}")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
