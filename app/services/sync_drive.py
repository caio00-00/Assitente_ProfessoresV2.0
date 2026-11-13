import re
import os
import unicodedata
from typing import Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from app.core.config import get_settings

settings = get_settings()


_SERVICO_CACHE = {"servico": None}


def get_drive_service():
    """
    v4: o cliente do Drive é criado uma vez por processo e reaproveitado
    (antes era recriado a cada busca, duas vezes por relatório).
    """
    if _SERVICO_CACHE["servico"] is None:
        _SERVICO_CACHE["servico"] = _criar_drive_service()
    return _SERVICO_CACHE["servico"]


def _criar_drive_service():
    import json
    import base64

    creds_b64 = os.environ.get('GOOGLE_CREDENTIALS_B64')
    if creds_b64:
        try:
            creds_json = json.loads(base64.b64decode(creds_b64).decode('utf-8'))
            creds = Credentials.from_service_account_info(
                creds_json,
                scopes=[
                    'https://www.googleapis.com/auth/drive.readonly',
                    'https://www.googleapis.com/auth/drive.metadata.readonly'
                ]
            )
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            print(f"❌ ERRO ao carregar credenciais da env var: {str(e)}")

    credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
    if not os.path.isabs(credentials_path):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        credentials_path = os.path.join(base_dir, credentials_path)

    if not os.path.exists(credentials_path):
        print(f"⚠️ AVISO: Arquivo de credenciais não encontrado em {credentials_path}")
        return None

    try:
        creds = Credentials.from_service_account_file(
            credentials_path,
            scopes=[
                'https://www.googleapis.com/auth/drive.readonly',
                'https://www.googleapis.com/auth/drive.metadata.readonly'
            ]
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"❌ ERRO ao inicializar Google Drive Service: {str(e)}")
        return None


def normalize_for_search(text: str) -> str:
    """
    Remove acentos, espaços e caracteres especiais, converte para minúsculo.
    Resultado: só letras e números colados, sem espaços.
    """
    if not text:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', text)
    text = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    text = text.lower()
    text = re.sub(r'[^a-z0-9]', '', text)
    return text


def extrair_prefixo_ate_data(nome: str) -> tuple:
    """
    Separa o nome em prefixo (antes da data) e data normalizada.
    Ex: "EM 3 MANHÃ QUÍMICA 20 04 26 CONTEÚDO"
        → ("em3manhaquimica", "200426")
    """
    match = re.search(r'(\d{2})\s(\d{2})\s(\d{2})', nome)
    if not match:
        return normalize_for_search(nome), ""

    antes_data = nome[:match.start()].strip()
    dia, mes, ano = match.groups()
    data_norm = f"{dia}{mes}{ano}"
    prefixo_norm = normalize_for_search(antes_data)

    return prefixo_norm, data_norm


# Reunião (out/2026): a coleta não depende da extensão no nome (.mp4 / .pdf).
# Vale o TIPO do arquivo no Drive: vídeo (qualquer formato) ou PDF. O nome é comparado
# sem a extensão — "AULA X.mp4", "AULA X.mov" e "AULA X" (sem extensão) são o mesmo nome.
FILTRO_VIDEO = "mimeType contains 'video/'"
FILTRO_PDF = "mimeType = 'application/pdf'"
_RE_EXT = re.compile(r"\.[A-Za-z0-9]{2,5}$")


def sem_extensao(nome: str) -> str:
    """'AULA X.mov' → 'AULA X'; 'AULA X' fica igual."""
    return _RE_EXT.sub("", (nome or "").strip()).strip()


def _eh_video(file: dict) -> bool:
    return (file.get("mimeType") or "").startswith("video/")


def _eh_pdf(file: dict) -> bool:
    return (file.get("mimeType") or "") == "application/pdf"


def _buscar_por_nome_e_tipo(service, nome_alvo: str, filtro_mime: str, aceitar) -> Optional[dict]:
    """
    Busca o arquivo pelo nome (sem extensão) e pelo tipo. Primeiro o nome inteiro; se não
    achar, por palavras do nome — sempre conferindo o nome normalizado (sem acento, espaço
    e extensão) e o tipo do arquivo.
    """
    nome_base = sem_extensao(nome_alvo)
    if not nome_base:
        return None
    alvo = normalize_for_search(nome_base)
    seguro = nome_base.replace("'", "\\'")
    words = [w.replace("'", "\\'") for w in re.split(r"\s+", nome_base) if w]
    consultas = [f"name contains '{seguro}'"]
    if len(words) > 1:
        consultas.append(" and ".join(f"name contains '{w}'" for w in words))
    for cond in consultas:
        res = service.files().list(
            q=f"{cond} and ({filtro_mime}) and trashed = false",
            fields="files(id, name, webViewLink, size, createdTime, mimeType, md5Checksum, parents)",
            pageSize=20,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives",
        ).execute()
        iguais = []
        for file in res.get("files", []):
            nome = file.get("name", "")
            mesmo_nome = alvo in (normalize_for_search(sem_extensao(nome)), normalize_for_search(nome))
            if aceitar(file) and mesmo_nome:
                iguais.append(file)
        if iguais:
            return escolher_melhor_arquivo(iguais)
    return None


def _pastas_oficiais() -> set:
    ids = {settings.GOOGLE_DRIVE_VIDEOS_FOLDER_ID, settings.GOOGLE_DRIVE_PDFS_FOLDER_ID}
    return {i for i in ids if i and i != "id_pendente"}


def escolher_melhor_arquivo(arquivos: list) -> dict:
    """
    v4: com mais de um arquivo de mesmo nome (cópia, versão antiga, arquivo em
    outra pasta), antes valia o primeiro que o Drive devolvesse. Agora:
    1. prefere o que está numa pasta oficial (quando configurada);
    2. depois o maior arquivo (vídeo incompleto é menor);
    3. depois o mais recente.
    """
    oficiais = _pastas_oficiais() if getattr(settings, "GOOGLE_DRIVE_RESTRINGIR_PASTAS", True) else set()

    def chave(f):
        na_pasta = bool(oficiais & set(f.get("parents") or []))
        return (na_pasta, int(f.get("size") or 0), f.get("createdTime") or "")

    return sorted(arquivos, key=chave, reverse=True)[0]


def buscar_video_no_drive(nome_alvo: str):
    """Vídeo da aula no Drive: qualquer arquivo do tipo vídeo com o mesmo nome (extensão não importa)."""
    service = get_drive_service()
    if not service:
        return None
    try:
        file = _buscar_por_nome_e_tipo(service, nome_alvo, FILTRO_VIDEO, _eh_video)
        if file:
            print(f"✅ Vídeo encontrado: '{file.get('name')}' ({file.get('mimeType')})")
        else:
            print(f"⚠️ Nenhum vídeo encontrado no Drive para: '{sem_extensao(nome_alvo)}'")
        return file
    except Exception as e:
        print(f"❌ ERRO na busca do Drive: {str(e)}")
        from googleapiclient.errors import HttpError
        if isinstance(e, HttpError) and e.resp.status in [423, 429]:
            raise e
        return None


def buscar_slide_no_drive(nome_alvo: str):
    """PDF da aula no Drive: arquivo do tipo PDF com o mesmo nome (extensão no nome não importa)."""
    service = get_drive_service()
    if not service:
        return None
    try:
        file = _buscar_por_nome_e_tipo(service, nome_alvo, FILTRO_PDF, _eh_pdf)
        if file:
            print(f"✅ PDF encontrado: '{file.get('name')}'")
        else:
            print(f"⚠️ Nenhum PDF encontrado no Drive para: '{sem_extensao(nome_alvo)}'")
        return file
    except Exception as e:
        print(f"❌ ERRO na busca de PDF no Drive: {str(e)}")
        return None
