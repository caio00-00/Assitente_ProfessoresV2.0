from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

# Broker e backend no Redis. No Docker o host é o serviço "redis"; com senha:
# redis://:SENHA@redis:6379/0
REDIS_URL = settings.REDIS_URL

celery_app = Celery("worker", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    imports=["app.tasks.worker", "app.services.email_service"],
    # v4: sem isto o Redis reentrega tarefas agendadas com mais de 1 h de atraso
    # (a verificação inicial espera ~2,5 h) e a mesma verificação rodava em dobro.
    broker_transport_options={"visibility_timeout": settings.CELERY_VISIBILITY_TIMEOUT_SECONDS},
    result_backend_transport_options={"visibility_timeout": settings.CELERY_VISIBILITY_TIMEOUT_SECONDS},
    result_expires=86400,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "sincronizacao-noturna-drive-3am": {
        "task": "sincronizacao_noturna_drive",
        "schedule": crontab(hour=3, minute=0),
    },
    "reprocessar-nao-verdes-a-cada-30min": {
        "task": "reprocessar_vermelhos_drive",
        "schedule": crontab(minute="*/30"),
    },
}
