# Análise de Mensageria e Envio de E-mails ✉️

Este documento audita o fluxo de criação de usuários e o disparo de senhas do sistema no que tange ao IAM (Identity and Access Management).

---

## 🛤️ 1. A Rota de Criação de Usuários
Os novos perfis não são abertos ("Sign Up" livre). O sistema opera puramente na base de **Convites** geridos por administradores.
*   **A Rota:** `POST /api/v1/auth/invite`
*   **Arquivo Localizado:** `app/api/rotas_auth.py`
*   **O Comportamento:** A rota gera o utilizador no banco (`User`) marcando sua `hashed_password` temporariamente como nula e atribuindo um `invite_token` (validador único) com duração de 24 horas.

---

## 📤 2. O Conteúdo do Disparo de E-mail
Imediatamente após a gravação da "conta fantasma" no banco, a rota chama a função assíncrona `send_invite_email`.
O objetivo dessa função não é enviar uma "senha limpa provisória" (o que feriria princípios de segurança), mas sim **um Link de Ativação** do próprio sistema.
*   **A Mensagem:** `"Sua conta foi criada. Ative-a aqui: http://localhost:8000/confirm?token={token}"`
Nesse instante, o usuário receberá o link para ele mesmo digitar e registrar sua própria senha.

---

## ⚡ 3. Síncrono, Background Task ou Celery?
Embora o projeto possua referências ao Redis e Celery no arquivo de configuração global, para a missão crítica de envio de e-mails, o desenvolvedor optou pela elegância do **FastAPI Background Tasks**.

*   **A Chamada no Código:** `background_tasks.add_task(send_invite_email, new_user.email, new_user.full_name, token)`
*   **Veredito de Velocidade:** O processo não prende o Frontend numa tela de "Carregando...". Ele é retornado (**status HTTP 200 OK**) instantaneamente ao assistente de cadastro. Logo depois da devolução fluida, o servidor FastAPI dispara a *task* de abrir o socket SMTP e enviar a mensagem rodando em background no mesmo _Event Loop_ do backend, dispensando totalmente a complexidade de manter o trabalhador Celery apenas para e-mails.

---

## ⚙️ 4. Configuração SMTP e Tolerância a Erros
O arquivo conector que constrói as carcaças vitais dos envios foi mapeado com excelência:
*   **Local:** `app/services/email_service.py`
*   **Variáveis em Uso:** Sim! Ele importa diretamente o `get_settings()` de `app/core/config.py` e extrai fielmente `settings.SMTP_USER` e `settings.SMTP_PASSWORD`.
*   **Boas Práticas de Fallback:** O código é à prova de crashes de `.env`. Ele usa lógicas de limpeza (`replace('"', '')`) para caso alguém digite aspas na AWS ou no servidor de deploy no Docker, além de ter um print `⚠️ SMTP não configurado` que revela o token impresso no console puro (terminal), destravando o desenvolvedor que cria a conta na própria máquina dele localmente mas optou por não preencher o Gmail de disparo!
*   **Gateway e Portas:** Construído sobre o conector `aiosmtplib`, prevê dinamicamente o uso moderno do SSL (`use_tls` para porta *465* restrita) ou o TLS flexível (`start_tls` para porta *587* Gmail), englobando qualquer cenário!
