import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.sync_drive import buscar_video_no_drive, buscar_slide_no_drive

def run_qa():
    with open('app/data/FICHEIRO GERADO.txt', 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    # Process first 10 for testing
    count = 0
    for line in lines[:15]:
        line = line.strip()
        if not line: continue
        
        try:
            # 1. Video
            video = buscar_video_no_drive(line)
            v_name = video.get('name') if video else "NÃO ENCONTRADO"
            v_link = video.get('webViewLink') if video else "NÃO ENCONTRADO"

            # 2. Slide
            slide = buscar_slide_no_drive(line)
            s_name = slide.get('name') if slide else "NÃO ENCONTRADO"
            s_link = slide.get('webViewLink') if slide else "NÃO ENCONTRADO"

            dupe_warning = ""
            if v_link != "NÃO ENCONTRADO" and v_link == s_link:
                dupe_warning = " [ERRO DE DUPLICIDADE]"

            print(f"{line} | {v_name} | {v_link} | {s_name} | {s_link}{dupe_warning}")
            count += 1
        except Exception as e:
            print(f"FAILED on {line}: {e}")
        
        time.sleep(0.1)

if __name__ == '__main__':
    run_qa()
