# PRD: Módulo de Verificação do Sistema (System Health Check & Diagnóstico de Infraestrutura)

## 1. Introdução / Visão Geral

O Canal Educação (Assistente de Professores v3.0) opera com múltiplos serviços integrados: API FastAPI, banco de dados PostgreSQL, mensageria/cache Redis, processamento assíncrono com Celery (Worker e Beat) e integração externa com a API do Google Drive.

Atualmente, não há uma forma padronizada e unificada para monitorar a integridade dessas dependências operacionais em tempo real e de forma automatizada. Este recurso implementa um mecanismo de **Verificação de Saúde do Sistema (Health Check)** com endpoints REST padronizados (`/api/v1/health` e `/api/v1/system/diagnostics`) e rotinas periódicas de diagnóstico em background, permitindo que ferramentas de observabilidade (Docker, Dokploy, Uptime Kuma, Prometheus) e administradores identifiquem rapidamente qualquer gargalo ou queda de serviço antes que afete os usuários finais.

---

## 2. Objetivos (Goals)

- Fornecer um endpoint leve de liveness/readiness probe (`/api/v1/health`) para orquestradores de contêiner e balanceadores de carga.
- Disponibilizar um endpoint detalhado de diagnóstico de infraestrutura (`/api/v1/system/diagnostics`) com verificação ponta a ponta dos componentes:
  - Conexão e tempo de resposta do PostgreSQL.
  - Conexão, latência e uso de memória do Redis.
  - Disponibilidade de workers ativos e fila do Celery.
  - Status e autenticação do cliente Google Drive API v3.
- Implementar uma tarefa assíncrona periódica no Celery Beat para registrar o histórico de saúde do sistema e salvar logs estruturados em caso de degradação.
- Manter o módulo 100% como **somente leitura (read-only)**, sem interferência ou mutação de dados da aplicação.

---

## 3. Histórias de Usuário (User Stories)

### US-001: Endpoint Leve de Liveness e Readiness Probe
**Descrição:** Como orquestrador de contêineres (Docker / Dokploy), quero consultar um endpoint rápido `/api/v1/health` para saber se a API está de pé e apta a receber tráfego.

**Critérios de Aceitação:**
- [ ] Retorna status HTTP 200 com payload JSON `{"status": "healthy", "timestamp": "ISO-8601"}` se a API estiver responsiva.
- [ ] Tempo de resposta do endpoint inferior a 50ms sob carga normal.
- [ ] Não realiza consultas pesadas ou bloqueantes no banco de dados.
- [ ] Testes unitários e de rota passam com 100% de sucesso.

---

### US-002: Verificação de Conectividade do PostgreSQL
**Descrição:** Como engenheiro de DevOps / Administrador, quero validar o status da conexão com o banco de dados e a latência de consulta.

**Critérios de Aceitação:**
- [ ] Executa query simples de verificação (`SELECT 1`) com timeout configurado (ex: 3s).
- [ ] Retorna status do banco: `status` ("connected" / "error"), `latency_ms` e mensagem de erro em caso de falha.
- [ ] Se o banco estiver inacessível, o status geral do diagnóstico reflete `degraded` ou `unhealthy` com código HTTP apropriado (HTTP 503 quando indisponível).
- [ ] Testes de integração cobrindo cenários de sucesso e simulação de falha de conexão.

---

### US-003: Verificação do Redis e Filas do Celery
**Descrição:** Como administrador, quero saber se o broker Redis está acessível e se há workers do Celery ativos para processar tarefas assíncronas de conformidade.

**Critérios de Aceitação:**
- [ ] Testa comando `PING` no Redis e mede latência em milissegundos.
- [ ] Inspeciona workers ativos do Celery via `celery.control.inspect().ping()` com timeout restrito (ex: 2s).
- [ ] Retorna contagem de workers ativos encontrados e status das filas.
- [ ] Trata timeouts graciosamente sem travar a resposta da requisição.
- [ ] Testes unitários cobrindo cenários com Redis online/offline e workers ativos/inativos.

---

### US-004: Verificação de Autenticação da Google Drive API
**Descrição:** Como administrador, quero verificar se as credenciais do Google Drive (Service Account / OAuth) continuam válidas e acessíveis pela aplicação.

**Critérios de Aceitação:**
- [ ] Realiza chamada leve de validação na API do Google Drive (ex: `about.get(fields="user")` ou checagem de permissão nas pastas configuradas).
- [ ] Retorna status do serviço Drive: `status` ("connected" / "invalid_credentials" / "timeout" / "not_configured"), e-mail da conta de serviço vinculada e tempo de resposta.
- [ ] Trata exceções da Google API sem propagar crash para a rota.
- [ ] Testes unitários com mocks da API do Google.

---

### US-005: Endpoint Unificado de Diagnóstico Sob Demanda (`/api/v1/system/diagnostics`)
**Descrição:** Como sistema de monitoramento ou administrador, quero consultar um payload JSON completo com a saúde consolidada de todos os serviços.

**Critérios de Aceitação:**
- [ ] Rota protegida por autenticação (JWT de Admin ou Header `X-Health-Key` para agentes externos de monitoramento).
- [ ] Retorna status global: `healthy` (todos OK), `degraded` (algum serviço secundário falhou) ou `unhealthy` (banco de dados ou API inoperantes).
- [ ] Payload inclui seções detalhadas: `database`, `redis`, `celery_workers`, `google_drive` e `system_info` (tempo de atividade/uptime, versão da aplicação, versão do Python).
- [ ] Tratamento assíncrono para executar as checagens em paralelo quando possível (via `asyncio.gather`), reduzindo tempo total de resposta.
- [ ] Testes de API validando estrutura do schema Pydantic de resposta.

---

### US-006: Tarefa Periódica em Background via Celery Beat
**Descrição:** Como mantenedor do sistema, quero que o sistema registre periodicamente no log o status de saúde dos serviços para auditoria e detecção preventiva de falhas.

**Critérios de Aceitação:**
- [ ] Criada tarefa periódica Celery `tasks.check_system_health_task` agendada no Beat (intervalo configurável via `.env`, padrão: a cada 15 minutos).
- [ ] Registra log em nível `INFO` quando todos os serviços estão saudáveis.
- [ ] Registra log em nível `ERROR` / `WARNING` com detalhes específicos quando qualquer serviço falha ou responde com alta latência.
- [ ] Armazena o último resultado de verificação no Redis (chave com TTL) para consulta ultrarrápida em cache.

---

## 4. Requisitos Funcionais (Functional Requirements)

- **FR-1:** O sistema deve expor `GET /api/v1/health` retornando `200 OK` para checagem rápida de liveness sem autenticação.
- **FR-2:** O sistema deve expor `GET /api/v1/system/diagnostics` retornando diagnóstico detalhado de cada serviço (PostgreSQL, Redis, Celery, Google Drive, Uptime).
- **FR-3:** A rota `/api/v1/system/diagnostics` deve aceitar autenticação via Bearer Token JWT (usuário com perfil `admin`) ou via token estático de monitoramento (`X-Health-Check-Key` configurável no `.env`).
- **FR-4:** O diagnóstico do banco de dados deve executar uma consulta com timeout máximo de 3 segundos e reportar latência em ms.
- **FR-5:** O diagnóstico do Redis deve testar comando `PING` e retornar status de conectividade e tempo de resposta.
- **FR-6:** O diagnóstico do Celery deve inspecionar workers online com timeout de 2 segundos, reportando lista e quantidade de nós ativos.
- **FR-7:** O diagnóstico do Google Drive deve testar a validade das credenciais `credentials.json` / `credentials2.json` e o acesso à API v3.
- **FR-8:** O status geral (`overall_status`) deve ser calculado com a seguinte regra:
  - `healthy`: Todos os serviços operacionais.
  - `degraded`: Google Drive ou Celery offline, mas Banco de Dados e Redis operacionais.
  - `unhealthy`: Banco de Dados PostgreSQL ou Redis inacessíveis.
- **FR-9:** As checagens devem ser executadas com concorrência não-bloqueante (`asyncio`).
- **FR-10:** A tarefa `check_system_health_task` deve ser executada a cada 15 minutos no Celery Beat, salvando o snapshot mais recente no Redis (cache com TTL de 30 min).

---

## 5. Fora de Escopo (Non-Goals)

- Nenhuma ação de escrita ou modificação de banco de dados (o módulo é estritamente diagnóstico / read-only).
- Nenhuma ação automática de restart de serviços, contêineres ou processos.
- Nenhuma interface gráfica complexa de gerenciamento ou dashboard frontend nesta fase (consumo exclusivo via API REST e logs).
- Nenhum envio de SMS ou notificações push customizadas (integração será delegada para as ferramentas de observabilidade externas consumindo a API).

---

## 6. Considerações Técnicas e Arquitetura

### Estrutura de Arquivos Proposta:
- `app/schemas/health.py`: Schemas Pydantic para validação do retorno dos diagnósticos (`ComponentStatus`, `HealthCheckResponse`, `DiagnosticsResponse`).
- `app/services/health_service.py`: Camada de serviço contendo a lógica isolada de verificação de cada componente (DB, Redis, Celery, Google Drive).
- `app/api/v1/endpoints/health.py`: Endpoints FastAPI para `/health` e `/system/diagnostics`.
- `app/tasks/health_tasks.py`: Tarefa Celery periódica para checagem em background.

### Variáveis de Ambiente (`.env`):
- `HEALTH_CHECK_SECRET_KEY`: Chave opcional para header `X-Health-Check-Key` (monitoramento externo).
- `HEALTH_CHECK_CRON_MINUTES`: Intervalo de execução periódica no Beat (padrão: 15).
- `HEALTH_CHECK_DB_TIMEOUT_SEC`: Timeout para consulta de banco (padrão: 3).

---

## 7. Métricas de Sucesso (Success Metrics)

- **Tempo de Resposta**: Endpoint `/api/v1/health` responde em menos de 50ms; `/api/v1/system/diagnostics` responde em menos de 1000ms com todos os serviços saudáveis.
- **Confiabilidade**: 0% de falsos positivos em alertas de indisponibilidade causados por travamento da rota de verificação.
- **Isolamento**: Falha em um serviço externo (como Google Drive) não pode derrubar a rota ou gerar HTTP 500 não tratado.

---

## 8. Perguntas em Aberto (Open Questions)

- Deseja que a rota de diagnóstico detalhado exponha métricas de uso de disco/memória do servidor (via `psutil`), ou apenas status das conexões de serviços?
- Qual é o serviço de monitoramento primário atualmente em uso no ambiente de produção (ex: Dokploy health checks, Uptime Kuma, Prometheus/Grafana)?
