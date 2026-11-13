from app.services.sync_drive import get_drive_service
import os

def list_slides():
    service = get_drive_service()
    folder_id = "1kofyW66jeRT0dXneD3qZZKQAeHNpkBR3"
    query = f"'{folder_id}' in parents and trashed = false"
    
    results = service.files().list(
        q=query, 
        fields="files(id, name, mimeType)",
        pageSize=1000,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    
    items = results.get('files', [])
    print(f"Encontrados {len(items)} arquivos na pasta de slides:")
    for item in items:
        print(f"- {item['name']} ({item['mimeType']})")

if __name__ == "__main__":
    list_slides()
