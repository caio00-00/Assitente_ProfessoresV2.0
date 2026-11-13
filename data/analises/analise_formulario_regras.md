# Análise de Regras de Negócio e Comportamento do Formulário (V3.0)

Este documento centraliza as dependências, gatilhos (cascatas) e agrupamentos dinâmicos que o formulário de Aula (`report_form.html`) exige da API do sistema Pydantic/FastAPI, com ênfase no fluxo lógico de preenchimento.

---

## 🔀 1. Gatilhos de Cascata (Dependências de Select)

O preenchimento não é estático. Certos campos ditam obrigatoriedades e disparam requisições ativas para o próximo nível da cadeia:

*   **A Turma afeta a Disciplina**: Inicialmente a disciplina fica travada ("Selecione a turma primeiro"). Ao escolher uma Turma, o evento JS `onTurmaChange()` é engatilhado. 
    *(Obs. Técnica: Estranhamente, a rota do frontend não envia o ID da turma no link de Disciplina. Ele chama a rota global e carrega todas as disciplinas cadastradas no banco).*
*   **A Disciplina afeta o Professor**: Apenas após ter uma disciplina definida em tela, o Javascript roda o `onDisciplinaChange()` e libera os professores que ministram AQUELA matéria, trancando os outros de aparecerem na lista e evitando casamentos errôneos como "Matemática -> Prof. de Português".

---

## 👁️ 2. Campos Condicionais e Lógicas Híbridas (Dynamic UI)

Muitas divs do pacote `report_form.html` rodam uma função mestra `toggleFormLogic()` e `toggleConditional()`, ativando e sumindo com partes da tela:

| Condição Engatilhada | O que SOME / TRAVA? | O que SURGE na tela? |
| :--- | :--- | :--- |
| **Opção Regular: "Não"** (Aula Avulsa) | Oculta **Grade** (`Turma`, `Disciplina`, `Professor`, `Interação Aluno`) e remove submissões obrigatórias desses campos para `null`. | Surge aba **Aula Avulsa** (`Ticket Number`, `Horário Início`, `Horário Fim`). |
| **Tipo de Aula:** Contém a palavra "Gravação" (ou Aula Avulsa) | (Nada). | Surge o bloco **Informações de Gravação** (`Diretor Imagem`, `Needs Editing`, `Link Youtube`). |
| **Interações:** Tipo "Outras" | (Nada). | Surge o input aberto **"Descreva a Interação"** (`interacao_outras_desc`). |
| **Recursos:** Checkbox "Outro" | (Nada). | Surge o input aberto **"Descreva o Recurso"** (`recursos_outro_desc`). |
| **Material:** Problema "Sim" | (Nada). | Surge criador avulso de Tag HTML **"Materiais Problemáticos"** (`prob_mat_nome` e descrição). |
| **Professor:** Substituição "Sim" | (Nada). | Surge o Dropdown **"Professor Substituto"** listando a gama de todos para escolha. |
| **Operacional:** Atraso "Sim" | (Nada). | Surge o seletor **"Minutos"** + input texto **"Justificativa"**. |

---

## 🌐 3. Pré-requisitos de Backend e Rotas (De onde saem os dados?)

Para criar o cenário acima, o sistema recruta ativamente dados mesclados, tanto da API de forma remota, quanto *Hardcoded* no banco local:

### Dados Alimentados via API REST (Banco de Dados Dinâmico):
1.  **Turmas:** `<select id="turma_id">` -> Puxa a listagem da rota `GET /api/v1/turmas/`.
2.  **Disciplinas:** `<select id="disciplina_id">` -> Puxa lista global via `GET /api/v1/reports/lookup/disciplinas`.
3.  **Professores Locais:** `<select id="professor_id">` -> Puxa da rota restrita `GET /api/v1/reports/lookup/professores-por-disciplina/{id}`.
4.  **Professores Substitutos:** `<select id="professor_substituto_id">` -> Puxa todo o pool da rota `GET /api/v1/reports/lookup/professores`.

### Dados Estáticos (Hardcoded / Fixos via Tag HTML):
O Frontend possui os valores cravados na tela (sem chamada a API). Contudo, o módulo *Schema* `app/schemas/class_report.py` do seu Pydantic valida agressivamente esses nomes garantindo que sejam respeitados os cases caso alguém consiga furar a view original. São eles:
1.  **Estúdio:** (`Estúdio 01` até `Estúdio 09`, `Externo`).
2.  **Turno:** (`Manhã`, `Tarde`, `Noite`, `FDS manhã`, etc).
3.  **Canais:** (`Canal SEDUC PI 1` até o `9`).
4.  **Tipos de Aula:** (`Videoconferência`, `Gravação estúdio`, `Manutenção de estúdio`, `UAPI`, `Planejamento`, ...).
5.  **Horários de Grade:** (`1º Horário` até o `8º Horário`). Mapeamento simples feito no dropdown.
