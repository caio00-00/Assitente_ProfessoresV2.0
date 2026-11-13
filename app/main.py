"""
Canal Educação v3.0 — Aplicação Principal FastAPI.
Registra todas as rotas, middleware, CORS, WebSockets, e templates.
"""

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import Base, engine, get_db
from app.domain.exceptions.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BusinessRuleViolation,
    ConflictException,
    DomainException,
    EntityNotFoundException,
)

# Importa todos os modelos para garantir que as tabelas sejam criadas
from app.models import (  # noqa: F401
    AuditLog,
    ClassReport,
    Disciplina,
    DiretorImagem,
    Estudio,
    CanalIptvModel,
    SlotHorario,
    GradeVersao,
    Grade,
    Professor,
    ProfessorDisciplina,
    Turma,
    Unit,
    User,
    ImageDirectorReport,
    ImageDirectorLesson,
    ImageDirectorChecklistItem,
    ImageDirectorChecklistResponse,
    ImageDirectorCustomQuestion,
    ImageDirectorCustomAnswer,
    AgendamentoEstudio,
    BloqueioEstudio,
    EscalaDiaEstudio,
    EscalaFixaEstudio,
)

# Rotas
from app.api.rotas_auth import router as auth_router
from app.api.rotas_report import router as report_router
from app.api.rotas_turma import router as turma_router
from app.api.rotas_live import router as live_router
from app.api.rotas_cadastros import router as cadastros_router  # TASK 15
from app.api.rotas_configuracoes import router as configuracoes_router
from app.api.rotas_grade_versao import router as grade_versao_router
from app.api.websocket.rotas_grade_ws import router as ws_router
from app.api.rotas_externas import router as external_router  # API Externa M2M
from app.api.rotas_diretor_imagem import router as diretor_imagem_router  # v3.2
from app.api.rotas_agenda_estudios import router as agenda_estudios_router
from app.api.rotas_v4 import router as v4_router  # v4: Início, linha do tempo, histórico
from app.api.rotas_sistema import router as sistema_router  # v4.1: saúde, varredura do Drive, migração
from app.domain.enums.enums import TipoAulaEnum

settings = get_settings()
_docs_ligados = settings.DOCS_ENABLED and settings.ENVIRONMENT.lower() not in ("production", "prd", "prod")

# ─── Criação da App ──────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Sistema de Gestão de Relatórios de Aula — Canal Educação v4",
    # v4: em produção a documentação interativa fica desligada (expunha o mapa da API).
    docs_url="/docs" if _docs_ligados else None,
    redoc_url="/redoc" if _docs_ligados else None,
    openapi_url="/openapi.json" if _docs_ligados else None,
)

# ─── CORS ─────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Banco de dados ──────────────────────────────────────────────────
# v4: o banco é preparado pelo entrypoint (scripts/db_bootstrap.py: Alembic +
# create_all das tabelas faltantes). Antes isto rodava a cada import da API, em
# cada processo, sem controle de versão. AUTO_CREATE_TABLES=true mantém o
# comportamento antigo para quem sobe a API sem o entrypoint novo.
if settings.AUTO_CREATE_TABLES:
    from app.models.agenda_estudio import garantir_colunas_agenda  # noqa: E402

    Base.metadata.create_all(bind=engine)
    garantir_colunas_agenda(engine)

# ─── Static Files & Templates ────────────────────────────────────────

import os

static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")

# Cria diretórios se não existirem
os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)
# v4.1: as páginas sabem se há WebSocket (na Vercel não há)
templates.env.globals["tempo_real"] = settings.tempo_real

# ─── Error Handling Middleware ────────────────────────────────────────


@app.exception_handler(EntityNotFoundException)
async def entity_not_found_handler(request: Request, exc: EntityNotFoundException):
    return JSONResponse(
        status_code=404,
        content={"error": exc.code, "detail": exc.message},
    )


@app.exception_handler(ConflictException)
async def conflict_handler(request: Request, exc: ConflictException):
    return JSONResponse(
        status_code=409,
        content={"error": exc.code, "detail": exc.message},
    )


@app.exception_handler(BusinessRuleViolation)
async def business_rule_handler(request: Request, exc: BusinessRuleViolation):
    return JSONResponse(
        status_code=422,
        content={"error": exc.code, "detail": exc.message},
    )


@app.exception_handler(AuthenticationError)
async def auth_error_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(
        status_code=401,
        content={"error": exc.code, "detail": exc.message},
    )


@app.exception_handler(AuthorizationError)
async def authz_error_handler(request: Request, exc: AuthorizationError):
    return JSONResponse(
        status_code=403,
        content={"error": exc.code, "detail": exc.message},
    )


@app.exception_handler(DomainException)
async def domain_error_handler(request: Request, exc: DomainException):
    return JSONResponse(
        status_code=400,
        content={"error": exc.code, "detail": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Personaliza as mensagens de erro de validação (Pydantic/FastAPI).
    Remove prefixos técnicos como 'body.field: Value error' e retorna apenas a mensagem limpa.
    """
    errors = exc.errors()
    if not errors:
        return JSONResponse(status_code=422, content={"detail": "Erro de validação nos dados."})
        
    raw_msg = errors[0].get("msg", "Erro de validação nos dados enviados.")
    
    # Remove prefixos comuns do Pydantic para deixar a mensagem limpa
    clean_msg = raw_msg.replace("Value error, ", "").replace("Assertion failed, ", "")
    
    return JSONResponse(
        status_code=422,
        content={"detail": clean_msg},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    v4: erro inesperado não devolve mais o texto interno (nomes de tabela, SQL).
    O detalhe fica no log com um código que o usuário pode repassar ao suporte.
    """
    import logging
    import uuid as _uuid

    codigo = _uuid.uuid4().hex[:8]
    logging.getLogger("app.erros").exception("erro %s em %s %s", codigo, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Erro interno. Se continuar, informe o código {codigo} ao suporte.", "codigo": codigo},
    )


# ─── Registro das Rotas ──────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(turma_router)
app.include_router(report_router)
app.include_router(live_router)
app.include_router(cadastros_router)  # TASK 15
app.include_router(configuracoes_router)
app.include_router(grade_versao_router)
app.include_router(ws_router)
app.include_router(external_router)  # API Externa M2M — Estudologia
app.include_router(diretor_imagem_router)  # Relatório do Diretor de Imagem — v3.2
app.include_router(agenda_estudios_router)  # Agenda de Estúdios (Admin / Diretor-Chefe)
app.include_router(sistema_router)  # v4.1: /api/v1/sistema/*
app.include_router(v4_router)  # v4: painel Início, linha do tempo da aula, histórico de versões


# ─── Health Check ─────────────────────────────────────────────────────


@app.get("/ping")
def health_check():
    return {
        "status": "online",
        "version": settings.APP_VERSION,
        "app": settings.APP_NAME,
    }


# ─── Frontend Pages (Jinja2) ─────────────────────────────────────────


@app.get("/")
def index(request: Request):
    """Redireciona para login ou dashboard."""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/inicio")
def inicio_page(request: Request):
    """v4: painel Início — o que precisa de quem está logado."""
    return templates.TemplateResponse("inicio.html", {"request": request})


@app.get("/aula")
def aula_page(request: Request):
    """v4: linha do tempo de uma aula (?cr=<id> ou ?idr=<id>)."""
    return templates.TemplateResponse("aula.html", {"request": request})


@app.get("/dashboard")
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/grade")
def grade_page(request: Request):
    return templates.TemplateResponse("grade.html", {"request": request})


@app.get("/report")
def report_page(request: Request):
    return templates.TemplateResponse("report_form.html", {"request": request})


@app.get("/reports-audit")
def reports_audit_page(request: Request):
    """Tela de Relatórios e Auditoria (§5.3)."""
    return templates.TemplateResponse(
        "reports_audit.html",
        {
            "request": request,
            "tipo_aula_options": [e.value for e in TipoAulaEnum],
        },
    )


@app.get("/admin/users")
def admin_users_page(request: Request):
    return templates.TemplateResponse("admin_users.html", {"request": request})


@app.get("/admin/cadastros")
def admin_cadastros_page(request: Request):
    """Tela de CRUD de Professores, Disciplinas e Diretores (TASK 15)."""
    return templates.TemplateResponse("admin_cadastros.html", {"request": request})


@app.get("/admin/configuracoes")
def admin_configuracoes_page(request: Request):
    """Tela de configuração de infraestrutura."""
    return templates.TemplateResponse("admin_configuracoes.html", {"request": request})


@app.get("/diretor-imagem")
def diretor_imagem_page(request: Request):
    """Tela do Relatório do Diretor de Imagem (v3.2) — restrita por role no frontend/backend."""
    return templates.TemplateResponse("image_director_report_form.html", {"request": request})


@app.get("/diretor-imagem/grade")
def diretor_imagem_grade_page(request: Request):
    """Grade do diretor de imagem: por estúdio, nos turnos em que ele está escalado."""
    return templates.TemplateResponse("diretor_grade.html", {"request": request})


@app.get("/diretor-imagem/historico")
def diretor_imagem_historico_page(request: Request):
    """Histórico/auditoria dos Relatórios do Diretor de Imagem."""
    return templates.TemplateResponse("image_director_reports_list.html", {"request": request})


@app.get("/diretor-imagem/perguntas")
def diretor_imagem_perguntas_page(request: Request):
    """Administração de perguntas extras e checklist — restrita ao Diretor-Chefe/Admin/Gestor."""
    return templates.TemplateResponse("image_director_questions_admin.html", {"request": request})


@app.get("/agenda-estudios")
def agenda_estudios_page(request: Request):
    """Agenda de Estúdios — Admin e Diretor-Chefe editam; pedagógico e auditoria só consultam."""
    return templates.TemplateResponse("agenda_estudios.html", {"request": request})


@app.get("/confirm")
def confirm_page(request: Request):
    return templates.TemplateResponse("confirm.html", {"request": request})


@app.get("/forgot-password")
def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})


@app.get("/reset-password")
def reset_password_page(request: Request):
    return templates.TemplateResponse("reset_password.html", {"request": request})


@app.get("/live-monitor")
def live_monitor_page(request: Request, db: Session = Depends(get_db)):
    """Tela de Live Monitor NOC (§5.5)."""
    from app.models.turma import Turma
    from app.models.auxiliares import Grade
    from sqlalchemy import distinct
    import datetime
    
    turmas = db.query(Turma).order_by(Turma.nomenclatura_padrao).all()
    
    # Buscar horários reais da grade (distintos) em vez de range fixo
    horarios_db = (
        db.query(distinct(Grade.horario_inicio))
        .filter(Grade.horario_inicio != None)
        .order_by(Grade.horario_inicio)
        .all()
    )
    
    # Filtrar horários dummy (00:00 = GRAVAÇÃO) e formatar
    horarios = []
    for (h,) in horarios_db:
        formatted = h.strftime("%H:%M")
        if formatted != "00:00":  # Exclui GRAVAÇÃO
            horarios.append(formatted)
    
    # Fallback se não houver horários na base
    if not horarios:
        horarios = [f"{h:02d}:00" for h in range(7, 22)]
    
    estudios = [f"Estúdio {i:02d}" for i in range(1, 10)] + ["Externo"]
    today_formatted = datetime.date.today().strftime("%d de %B, %Y")

    return templates.TemplateResponse("live_monitor.html", {
        "request": request,
        "turmas": turmas,
        "horarios": horarios,
        "estudios": estudios,
        "today_formatted": today_formatted
    })