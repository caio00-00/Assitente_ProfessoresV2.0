# Mapeamento e Auditoria de Campos (V3.0)

Este documento foi gerado para servir como roteiro de correção e limpeza (Guia de Deploy). Ele mapeia as discrepâncias entre o preenchimento no Front-End e as regras rígidas do Back-End, e finaliza com as instruções para bloquear requisições defeituosas ainda na interface.

---

## 📊  1. Tabela Comparativa (Tela x Banco de Dados)

| Nome do Campo (UI → DB) | Estado Atual (Front & Banco) | Expectativa e Regra V3.0 |
| :--- | :--- | :--- |
| **Escolas Participantes** (`escolas_input` → `escolas_participantes`) | No Banco: `JSONB`.<br>No Front: Array de Strings dinâmico alimentado por texto livre pressionando *Enter*. | Deveria ser obrigatório para aulas conjuntas. Idealmente deve evoluir de *texto livre* para busca por IDs (`UUID`) em tabelas de `escolas` estruturadas para evitar sujeira tipográfica. |
| **Diretor de Imagem** (`diretor_imagem` → `diretor_imagem`) | No Banco: `String`.<br>No Front: Texto livre (`<input type="text">`). | Obrigatoriedade condicional (se "Gravação"). Atualmente é *String*, mas para métricas confiáveis deveria referenciar `diretor_imagem_id` (`UUID`) em tabela estruturada via lista Suspensa (Dropdown). |
| **Link do YouTube** (`youtube_link` → `youtube_link`) | No Banco: `String`.<br>No Front: Input URL. | Não deve aceitar salvamentos de links quebrados ou strings sujas (ex: "sem link ainda"). Exige validação prévia de Regex (ex: conter `youtu.be` ou `youtube.com`). |
| **Horários de Gravação** (`start_time`/`end_time` → id) | No Banco: `Time` (via Alembic).<br>No Front: Input nativo de tempo do navegador (`<input type="time">`) enviando string `HH:MM`. | **Máscara:** O Frontend deve enviar no mínimo `08:00`. O Backend deve forçar com que este formato se extraia no padrão Exportável da V3.0: `$HH:MM:SS$` (ex: `08:00:00 - 09:40:00`). |

---

## 🚨 2. Análise de Erro: O "Fantasma" dos UUIDs (Comprimento Null)

O sistema vira refém das rotas de exceção 422 (Unprocessable Entity) quando tenta persistir aulas Regulares usando "Turma", "Professor" ou "Disciplina" não selecionados.

### 🔍 Por que o Front envia `""`?
Os elementos da interface para estes três campos são `<select>`:
`<option value="">Selecione o professor...</option>`
`<option value="123e4567-e89b-12d3...">João</option>`

O Javascript cru da sua função `buildReportBody()` extrai os dados assim:
`professor_id: isAvulsa ? null : document.getElementById('professor_id').value`

Quando o usuário esquece de marcar a seleção (Option índice 0), o Javascript captura e transmite literalmente uma string vazia `""`. Quando a string vazia atinge a camada Pydantic do Backend – que espera um hash alfanumérico estrito do tipo `uuid.UUID` –, o ORM quebra na hora avisando que a string enviada não tem os 36 caracteres exigidos para chaves estrangeiras.

### 🛠️ Correção e Bloqueio: Intervenção Sugerida no Código (Front-End)

A mitigação recomendada é aplicar uma malha fina antes do gatilho assíncrono do Fetch, vetando o disparo se algum ID obrigatório for vazio ou inválido. 
**Insira esse trecho injetado nativamente no `submitReport(e)` ou `buildReportBody()` localizados em `report_form.html`:**

```javascript
    function submitReport(e) {
        if (e) e.preventDefault();
        
        const isAvulsa = document.getElementById('regular').value === 'Não';

        // Mapeamento nativo dos IDs a validar
        const turmaID = document.getElementById('turma_id').value.trim();
        const discID = document.getElementById('disciplina_id').value.trim();
        const profID = document.getElementById('professor_id').value.trim();

        // 🛡️ Regra de Bloqueio UUID (Evitando erro de servidor 422)
        if (!isAvulsa) {
            if (!turmaID || turmaID === "") {
                showToast("Erro: Selecione uma Turma válida antes de salvar.", "error");
                return;
            }
            if (!discID || discID === "") {
                showToast("Erro: Selecione uma Disciplina válida antes de salvar.", "error");
                return;
            }
            if (!profID || profID === "" || profID.length < 32) {
                showToast("Erro: Selecione um Professor válido (ID não detectado).", "error");
                return;
            }
        }

        // Caso tudo esteja limpo, o fluxo original prossegue
        const token = localStorage.getItem('access_token');
        const body = buildReportBody();
        
        // ... continuação com o Fetch POST/PUT ...
    }
```

Implementando o condicional acima, a aplicação blinda o banco de requisições sujas e garante uma melhor UX avisando ao Assistente exatamente qual Dropdown ele pulou acidentalmente.
