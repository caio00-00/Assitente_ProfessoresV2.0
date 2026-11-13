# Auditoria de Estrutura do Frontend (Templates & Form)

O sistema "Canal Educação" não utiliza um SPA desacoplado moderno puro (como um diretório `src/` com Vue/React separado em pastas de componentes), mas sim um modelo monolítico baseado em **Server-Side Rendering com Jinja2**, embutido na própria API (FastAPI).

Sendo assim, as respostas e as visões estão codificadas na pasta `app/templates/` e as rotas mapeadas globalmente em `app/main.py`.

---

## 🛣️ 1. Rotas Principais do Sistema

Analisando o arquivo roteador principal (`main.py`), temos as seguintes rotas que direcionam a renderização das telas para o usuário navegável:

| Rota Navbar | Arquivo Template Atrelado | Função Destinada |
|-------------|----------------------------|------------------|
| `/` & `/login`| `login.html` | Tela de autenticação incial. |
| `/dashboard` | `dashboard.html` | Dashboard analítico/inicial. |
| `/grade` | `grade.html` | Tabela / Grade de horários programados. |
| `/report` | **`report_form.html`** | Formulário de Criação/Edição de Relatórios de Aula. |
| `/reports-audit` | `reports_audit.html` | Auditoria de cumprimento/compliance e busca avançada. |
| `/live-monitor` | `live_monitor.html` | Tela NOC Monitor para transmissão ao vivo. |
| `/admin/users` | `admin_users.html` | Gestão de usuários do RBAC. |

*(Nota: As rotas de API que alimentam dinamicamente estas telas via Javascript puro estão debaixo do prefixo `/api/v1/`).*

---

## 📝 2. Relatório de Aula (O Componente)

O componente procurado – responsável por gerar a interface do Formulário de Aula – foi localizado fisicamente em:
📂 **`app/templates/report_form.html`**

Este arquivo é um blocão de HTML com o CSS/JS incorporado que invoca Endpoints e coleta as interações do assistente em `Vanilla Javascript`.

---

## 🗂️ 3. Mapeamento de Campos de Formulário

Abaixo estão as seções listadas na tela e os campos presentes para o controle dos Operadores.

**📌 Contexto Operacional**
*   Data da Aula (`data_aula` input[date])
*   Turno (`turno` select)
*   Estúdio (`estudio` select)
*   Turma (`turma_id` select) *— Populado via JS*
*   Disciplina (`disciplina_id` select) *— Cascata JS baseado na turma*
*   Professor(a) (`professor_id` select) *— Cascata JS baseado na disciplina*
*   Ticket Number, Horário Início, Horário Fim (Campos condicionais para Aula Avulsa)
*   Horário da Aula (`horario_aula` select numérico)
*   Regular (`regular` select)

**🎬 Detalhes da Execução**
*   Tipo de Aula (`tipo_aula` select)
*   Canal Utilizado (`canal_utilizado` select)
*   Conteúdo Ministrado (`conteudo_ministrado` input[text])
*   **Escolas Participantes (`escolas_input` input + Tag Handler)**
*   Interação Professor-Aluno (`interacao_professor_aluno` select)
*   Atividade Prática (`atividade_pratica` select)
*   Observações Turno da Manhã (`observacoes_manha` textarea)
*   Observações Gerais (`observacoes` textarea)

**📦 Recursos, Ocorrências e Gravação**
*   **Diretor de Imagem (`diretor_imagem` input[text])**
*   Necessita Edição? (`needs_editing` select)
*   **Link do YouTube (`youtube_link` input[url])**
*   Recursos Utilizados (Checkboxes condicionais)
*   Problema Material (Checkboxes de tags condicionais)
*   Houve Substituição? / Falta (`teve_substituicao`)
*   Houve Atraso? (`teve_atraso`, `minutos_atraso`)

---

## ✅ 4. Validação: Checkup V3.0 (Novos Inputs)

A inspeção confirmou **oficialmente** que **todos** os novos campos solicitados para a Versão 3.0 estão integrados visual e funcionalmente, sem falhas de input:

1. **Escola (Escolas Participantes)**: ✅ Presente na linha 161 (`#escolas_input`). A UI dele foi feita usando um input de texto onde o usuário aperta a tecla `Enter` e o Javascript embutido monta as "Tags" visuais dinamicamente antes de submeter ao Back.
2. **Diretor de Imagem**: ✅ Presente na linha 212 (`#diretor_imagem`). É um input de texto aberto para digitação do "Nome...", alojado dentro do Card condicional "Informações de Gravação".
3. **Link do YouTube**: ✅ Presente na linha 224 (`#youtube_link`). É do tipo `type="url"`, reforçando um pouco de validação web, abrigado também na card "Informações de Gravação".

O componente HTML de criação e submissão está pronto e adequado os schemas do Backend.
