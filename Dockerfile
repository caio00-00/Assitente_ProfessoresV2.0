FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# O entrypoint fica fora de /app: assim um compose que monta o código em /app
# (como o antigo, com ".:/app") não o substitui, e um checkout do Windows com
# fim de linha CRLF não quebra o bash.
RUN sed 's/\r$//' /app/entrypoint.sh > /usr/local/bin/canal-entrypoint \
    && chmod 755 /usr/local/bin/canal-entrypoint

# v4: o container não roda mais como root.
RUN useradd --create-home --uid 1000 app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# O entrypoint decide o que rodar: "api" (padrão), "worker", "beat" ou qualquer
# comando completo (ex.: o "uvicorn ..." que o Dokploy já usa). Para a API ele
# prepara o banco antes (scripts/db_bootstrap.py).
ENTRYPOINT ["/usr/local/bin/canal-entrypoint"]
CMD ["api"]
