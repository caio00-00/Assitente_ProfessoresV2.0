# Demandas e Regras de Negócio — Assistente de Professores

**Data:** 14/10/2026
**Origem:** reunião gravada (transcrição) + lista de ajustes solicitados
**Sistema:** Canal Educação / Assistente de Professores

---

## 1. Regras de negócio definidas na reunião

### 1.1 Caso 1 — Antecipação de aula

Toda antecipação gera **dois momentos**: a **gravação** e a **transmissão**. O que muda é quantas vezes isso pode ser faturado.

| Origem da antecipação | Momentos gerados | Faturamento na SEDUC |
|---|---|---|
| Solicitação da SEDUC | 1 estúdio p/ gravação + 1 estúdio p/ transmissão | **Cobra 2x** (tem chamado aberto) |
| Solicitação pessoal do professor | 1 estúdio p/ gravação + 1 estúdio p/ transmissão | **Cobra 1x** |

**Detalhamento do faturamento (quando é solicitação da SEDUC):**

- Cobra-se o diretor de imagem do dia da **gravação**.
- Cobra-se o diretor de imagem do dia da **transmissão**.
- O relatório precisa deixar explícito que existe chamado da SEDUC, para que a cobrança dupla seja justificada.

**Regra de consistência obrigatória (vale para todos os casos):**

> O relatório do **diretor de imagem** e o relatório do **assistente de professores** precisam estar com o **mesmo tipo de aula**.

- Gravação ↔ Gravação
- Transmissão ↔ Transmissão

Motivo: as **NPs são obrigatoriamente apenas gravação**. Se os dois relatórios divergirem, o faturamento quebra.

**Abrangência:** essa mesma estrutura atende tanto as NPs (gravação de estúdio) quanto as antecipações de aula — seja por solicitação da SEDUC, seja por solicitação do professor.

**Pendência:** definir como os dois momentos (gravação e transmissão) serão **apresentados no relatório**, de modo que quem for puxar o dado saiba exatamente o que puxar.

---

### 1.2 Caso 2 — Gap na virada de mês (mês de execução × mês de referência)

**Escopo:** aplica-se apenas a aulas **com data**.
**Não se aplica a cursos técnicos**, porque nesses o que vale é o número da aula, não a data.

**Situação típica:**
Professor falta uma aula na última semana de setembro e só consegue gravá-la em outubro.

| Dimensão | Mês considerado |
|---|---|
| **Faturamento** (cobrança na SEDUC) | Mês em que a aula **foi gravada** → outubro |
| **Registro na plataforma / pagamento do professor** | Mês de **referência** da aula → setembro |

**Regras:**

- Não existe cobrança retroativa: a aula é cobrada **dentro do mês em que foi executada**.
- **Data de corte:** último dia do mês (contagem do dia 1 ao último dia).
- O professor recebe pela aula que gravou, dentro do mês corrente da gravação.
- Para efeito de plataforma, a aula precisa continuar registrada no mês de referência (setembro, no exemplo).

**O que o sistema precisa passar a ter:**

1. Um **indicativo** no registro da aula do tipo: *"gravação por falta do professor, referente ao dia XX/XX"*.
2. No relatório, a **data da gravação** (para faturar) **e** a informação de que a aula é **referente a outra data** (mês anterior).
3. Separação clara entre **mês de execução** e **mês de referência**.

**Observação levantada na reunião:** parte dessas exceções é previsível antes do mês começar — quando o professor falta, já se tem a previsão de quando aquela aula será executada. Isso permite trabalhar com o escopo de exceções antecipadamente ("faturamento do que existiu" × "faturamento subentendido").

**Pendência:** definir a representação desses dois meses no sistema (campos, nomenclatura e como aparecem no relatório).

---

## 2. Ajustes solicitados no sistema

### 2.1 Relatórios

| # | Item |
|---|---|
| 1 | Modelar como o relatório será **emitido em `.xlsm`** |
| 2 | **Remover a coluna de diretores de imagem** no relatório, quando o perfil for **coordenador** |

### 2.2 Usabilidade geral

| # | Item |
|---|---|
| 3 | Incluir **autocomplete** nos campos **Turma** e **Professor** |
| 4 | **Alertas** devem ficar visíveis por **pouco tempo** (reduzir duração) |
| 5 | **Validar o arrastar (drag):** está sensível demais — mesmo soltando exatamente sobre um horário vazio, dispara alerta informando que está indo para uma grade horária |

### 2.3 Agendamento de estúdio (perfil Diretor-Chefe)

| # | Item |
|---|---|
| 6 | Quando o campo **Tipo** for **Evento**, exibir o campo **Nome do evento** para preenchimento |
| 7 | Em **Grade Horária**, trocar "Selecionar turma" por **Estúdio** |
| 8 | **Incluir o campo Chave** no formulário do Diretor-Chefe |

### 2.4 Formulário do Diretor de Imagem

Todos os campos abaixo devem vir **pré-preenchidos a partir do formulário do Diretor-Chefe**, exceto onde indicado:

| Campo | Comportamento |
|---|---|
| Diretor de imagem | Pré-preenchido |
| Data da aula | Pré-preenchido |
| Turno | Pré-preenchido |
| Estúdio | Pré-preenchido |
| **Turma** | **Remover** |
| Nome do evento | Pré-preenchido |
| Departamento solicitante | Pré-preenchido |
| Início e fim | Pré-preenchido |
| Número do chamado | Pré-preenchido |
| Responsável | Pré-preenchido |
| Link do YouTube | Pré-preenchido + **botão de copiar** |
| Chave | Pré-preenchido + **botão de copiar** (campo a ser incluído no formulário do Diretor-Chefe) |

**Complementos:**

- Botão de **copiar** tanto para **Link do YouTube** quanto para **Chave**.
- **Registrar link do YouTube e chave por turno.**

### 2.5 Gravação de estúdio e faturamento

| # | Item |
|---|---|
| 9 | Na área de **gravação de estúdio**, abrir uma **nova aba** para informar **o dia em que a aula está sendo gravada** |

**Finalidade:** servir de base para o faturamento, separando **data de gravação** e **data de exibição** (ver regra 1.2 — mês de execução × mês de referência).

---

## 3. Pendências em aberto

- [ ] Definir o **layout do relatório em `.xlsm`** (colunas, agrupamentos, filtros por perfil).
- [ ] Definir como **apresentar gravação e transmissão** no relatório para o Caso 1 (antecipação), incluindo a marcação de chamado da SEDUC para justificar a cobrança dupla.
- [ ] Definir os **campos de mês de execução × mês de referência** e como aparecem no relatório.
- [ ] Definir o **indicativo de "gravação por falta do professor, referente ao dia XX"** no registro da aula.
- [ ] Implementar a **trava de consistência** entre o relatório do diretor de imagem e o do assistente de professores (mesmo tipo de aula).
