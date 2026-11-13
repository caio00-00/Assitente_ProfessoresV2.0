#!/bin/bash
set -e

# Remove o arquivo de estado do beat (evita "Resource temporarily unavailable").
rm -f celerybeat-schedule 2>/dev/null || true

preparar_banco() {
  # RUN_MIGRATIONS=0 desliga (ex.: quando outro container já cuida disso).
  if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[entrypoint] preparando o banco (scripts/db_bootstrap.py)"
    python -m scripts.db_bootstrap
  fi
}

case "$1" in
  api)
    preparar_banco
    exec gunicorn app.main:app \
      --worker-class uvicorn.workers.UvicornWorker \
      --workers "${WEB_CONCURRENCY:-2}" \
      --bind 0.0.0.0:8000 \
      --timeout "${GUNICORN_TIMEOUT:-120}" \
      --access-logfile -
    ;;
  api-dev)
    preparar_banco
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ;;
  worker)
    exec celery -A app.tasks.worker.celery_app worker --loglevel="${CELERY_LOG_LEVEL:-info}"
    ;;
  beat)
    exec celery -A app.tasks.worker.celery_app beat --loglevel="${CELERY_LOG_LEVEL:-info}" \
      --schedule /tmp/celerybeat-schedule
    ;;
  *)
    # Comando completo vindo do Dokploy/compose (compatível com o deploy antigo).
    case "$*" in
      *uvicorn*|*gunicorn*) preparar_banco ;;
    esac
    exec "$@"
    ;;
esac
