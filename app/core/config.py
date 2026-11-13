"""
Canal Educação v3.0 — Configuração centralizada via Pydantic Settings.
Todas as variáveis sensíveis são carregadas do .env.
"""

import json
from functools import lru_cache
from typing import Annotated, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração da aplicação. Valores carregados do .env automaticamente."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # <--- ADICIONE ESTA LINHA AQUI
    )

    # --- Aplicação ---
    APP_NAME: str = "Canal Educação API"
    APP_VERSION: str = "4.0"
    DEBUG: bool = False

    # --- v4: ambiente e chaves de comportamento ---
    # ENVIRONMENT: "local", "hml" ou "production". Em "production" a SECRET_KEY
    # padrão é recusada e a documentação /docs fica desligada (salvo DOCS_ENABLED).
    ENVIRONMENT: str = "local"
    DOCS_ENABLED: bool = True
    # Compatibilidade com o deploy antigo: cria tabelas faltantes ao subir a API.
    # No v4 o banco é preparado pelo entrypoint (scripts/db_bootstrap.py).
    AUTO_CREATE_TABLES: bool = False
    # Limite de tentativas de login por e-mail+IP dentro da janela (minutos).
    LOGIN_MAX_ATTEMPTS: int = 8
    LOGIN_WINDOW_MINUTES: int = 15

    # --- Domínio da Aplicação (para links em e-mails) ---
    APP_DOMAIN: str = "https://assistentes.orossolucoes.com.br/"

    # --- Base de Dados ---
    POSTGRES_DB: str = "postgres-prd"
    POSTGRES_USER: str = "assistente_professores"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    COMPLIANCE_MAX_AGE_DAYS: int = 45
    @property
    def eh_vercel(self) -> bool:
        import os
        return self.PLATAFORMA.strip().lower() == "vercel" or os.environ.get("VERCEL") == "1"

    @property
    def modo_tarefas(self) -> str:
        """'celery' (fila com worker) ou 'direto' (roda na própria API)."""
        m = self.MODO_TAREFAS.strip().lower()
        if m in ("celery", "direto"):
            return m
        return "direto" if self.eh_vercel else "celery"

    @property
    def tempo_real(self) -> bool:
        """WebSocket da grade e do ao vivo. A Vercel não mantém WebSocket aberto."""
        return not self.eh_vercel

    @property
    def DATABASE_URL(self) -> str:
        # Override explícito por env (usado em testes/CI). Em produção não é
        # definido — a URL é montada a partir das POSTGRES_* abaixo.
        import os
        env_url = os.environ.get("DATABASE_URL")
        if env_url:
            return _normalizar_url_postgres(env_url)

        # v4.1: integração Supabase da Vercel. Ela cria POSTGRES_URL (pooler,
        # porta 6543) e também POSTGRES_HOST apontando para a conexão direta
        # db.<projeto>.supabase.co, que a Vercel não alcança (só IPv6). Por isso
        # o POSTGRES_URL tem preferência sobre montar a URL com POSTGRES_HOST.
        integracao = os.environ.get("POSTGRES_URL")
        if integracao:
            return _normalizar_url_postgres(integracao)

        # Tenta detectar se o host 'db' (docker) é o correto ou se devemos usar localhost
        host = self.POSTGRES_HOST
        if host in ["db", "canal_edu_db", "canal_edu_db"]:
            # Se Windows ou fora de docker, muda para localhost
            import os
            if os.name == 'nt' or not os.path.exists('/.dockerenv'):
                host = "localhost"
        
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{host}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://redis:6379/0"
    # Tarefas com atraso maior que este valor seriam reentregues pelo Redis.
    # Precisa ser maior que COMPLIANCE_INITIAL_DELAY_SECONDS.
    CELERY_VISIBILITY_TIMEOUT_SECONDS: int = 43200  # 12 h

    # --- Onde o sistema roda (v4.1) ---
    # "docker" (padrão): API + worker + beat + Redis, como no Dokploy.
    # "vercel": sem worker nem Redis. A busca no Drive roda direto na API, pelo
    # botão "Buscar no Drive" e pela rota /api/v1/sistema/varredura (chamada por
    # um cron); o banco usa conexão sem pool (serverless). Na Vercel isso é
    # detectado sozinho pela variável VERCEL=1 que ela mesma define.
    PLATAFORMA: str = "docker"
    # Vazio = automático pela plataforma. "celery" ou "direto" para forçar.
    MODO_TAREFAS: str = ""
    # Segredo das rotas de sistema (varredura do Drive, migração). Na Vercel o
    # cron manda "Authorization: Bearer <CRON_SECRET>".
    CRON_SECRET: str = ""
    # URL usada só para migrar o banco. No Supabase use o pooler em modo sessão
    # (porta 5432); vazio = DATABASE_URL trocando a porta 6543 por 5432.
    DATABASE_URL_MIGRACAO: str = ""
    # Quanto tempo (s) a varredura direta pode rodar numa chamada
    VARREDURA_TEMPO_MAX_SEGUNDOS: int = 50

    # --- Segurança JWT ---
    SECRET_KEY: str = "chave_secreta_provisoria_desenvolvimento"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 horas

    # --- Tokens de Convite ---
    INVITE_TOKEN_EXPIRE_HOURS: int = 24

    # --- Compliance Drive (busca de vídeo/slide) ---
    # A verificação NÃO roda na hora da finalização: aguarda este atraso inicial,
    # pois o vídeo/slide normalmente só chega ao Drive depois desse tempo. Evita o
    # "storm" de retries inúteis (arquivo ainda não existe) e o falso-vermelho.
    COMPLIANCE_INITIAL_DELAY_SECONDS: int = 9000     # ~2,5h (2 a 3 horas)
    # Após o atraso inicial, re-checa em intervalo FIXO até achar.
    COMPLIANCE_RETRY_INTERVAL_SECONDS: int = 900     # 15 min
    COMPLIANCE_MAX_RETRIES: int = 20                 # ~5h de re-checagem pós-atraso

    # --- SMTP (Email Transacional) ---
    # IMPORTANTE: não hardcode credenciais reais aqui. Defina SMTP_USER e
    # SMTP_PASSWORD no .env (nunca commitado — ver .gitignore). Se ficarem
    # vazios, o serviço de email apenas loga o link em vez de tentar (e
    # falhar) o envio com uma credencial inválida.
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@oroseducacao.page"
    SMTP_USE_TLS: bool = True

    # --- Domínios permitidos (vazio = qualquer email) ---
    # NoDecode: o valor do .env chega como texto para o validador abaixo (vazio, JSON ou
    # separado por vírgula). Sem isso o pydantic-settings tenta ler como JSON e falha com vazio.
    ALLOWED_EMAIL_DOMAINS: Annotated[List[str], NoDecode] = []

    # --- CORS ---
    CORS_ORIGINS: Annotated[List[str], NoDecode] = ["http://localhost:8000", "http://localhost:3000"]

    # --- Google Drive ---
    GOOGLE_DRIVE_VIDEOS_FOLDER_ID: str = "id_pendente"
    GOOGLE_DRIVE_PDFS_FOLDER_ID: str = "id_pendente"
    GOOGLE_APPLICATION_CREDENTIALS: str = "credentials.json"
    # v4: quando as pastas acima estão configuradas, a busca fica restrita a elas
    # (e subpastas diretas). Com "id_pendente" a busca continua em todo o Drive.
    GOOGLE_DRIVE_RESTRINGIR_PASTAS: bool = True
    # Tamanho mínimo para aceitar o vídeo (MB). Antes fixo em 100 no código.
    COMPLIANCE_MIN_VIDEO_MB: int = 100

    # --- API Externa M2M (Estudologia) ---
    EXTERNAL_API_KEY: str = ""

    @field_validator("ALLOWED_EMAIL_DOMAINS", "CORS_ORIGINS", mode="before")
    @classmethod
    def parse_list_from_string(cls, v):
        """Handles empty strings and JSON-encoded lists from .env."""
        if isinstance(v, list):
            return v
        if not v or v.strip() == "":
            return []
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else [str(parsed)]
        except (json.JSONDecodeError, TypeError):
            # Comma-separated fallback
            return [s.strip() for s in v.split(",") if s.strip()]


SECRET_KEY_PADRAO = "chave_secreta_provisoria_desenvolvimento"


@lru_cache()
def _normalizar_url_postgres(url: str) -> str:
    """Deixa a URL no formato que o SQLAlchemy + psycopg2 aceitam.

    - "postgres://" (padrão do Supabase/Heroku) vira "postgresql://";
    - tira parâmetros que não são do Postgres (o Supabase põe "supa=base-pooler.x"
      e o psycopg2 recusa a conexão com "invalid URI query parameter").
    """
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    partes = urlsplit(url)
    if not partes.query:
        return url
    aceitos = {
        "sslmode", "sslrootcert", "sslcert", "sslkey", "connect_timeout", "application_name",
        "options", "target_session_attrs", "keepalives", "keepalives_idle", "host", "port",
        "gssencmode", "channel_binding", "client_encoding",
    }
    params = [(k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True) if k in aceitos]
    return urlunsplit(partes._replace(query=urlencode(params)))


def get_settings() -> Settings:
    """Singleton cacheado da configuração."""
    s = Settings()
    if s.ENVIRONMENT.lower() in ("production", "prd", "prod") and (
        not s.SECRET_KEY or s.SECRET_KEY == SECRET_KEY_PADRAO
    ):
        raise RuntimeError(
            "SECRET_KEY padrão em produção. Defina SECRET_KEY nas variáveis do Dokploy."
        )
    return s
