# Lógica de cobrança da SEDUC: antecipada, reposição e uso de estúdio

Este documento explica como o sistema trata hoje (HML) a cobrança por uso de estúdio, com foco no pedido da SEDUC. A explicação segue uma situação real, do agendamento até a planilha de faturamento. No fim estão as perguntas que ainda precisam da sua confirmação.

---

## 1. A regra combinada

- **Cobramos o uso de estúdio.** Se o estúdio foi usado e está na Agenda, há cobrança.
- **Pedido da SEDUC cobra duas vezes:** o uso do estúdio para **gravar** e o uso do estúdio para **transmitir/exibir**. É a única exceção.
- **Pedido do Canal Educação ou do professor cobra uma vez só**, quando a aula vai ao ar.
- **O professor é pago uma vez só, na transmissão**, mesmo quando a SEDUC paga duas vezes pelo estúdio.
- **Quem informa se o pedido é da SEDUC é o diretor-chefe, na Agenda**, com o nº do chamado. O assistente e o diretor de imagem não decidem isso.

---

## 2. Situação 1: aula antecipada pedida pela SEDUC

> A SEDUC avisa que o professor de Química da turma EM 2 MANHÃ vai viajar. A aula de **quarta, 28/10, das 08:30** será gravada antes, na **segunda, 26/10, às 14:00**, no Estúdio 2. Chamado nº 18097.

**Passo 1. Diretor-chefe, na Agenda (segunda, 26/10)**
- Cria o agendamento do tipo **Gravação antecipada** no Estúdio 2, das 14:00 às 15:00.
- Em **Solicitação da SEDUC?**, marca **Sim — SEDUC (cobra gravação + exibição)**. Com isso, o **nº do chamado (18097) passa a ser obrigatório**.
- Em **Data da exibição**, coloca 28/10.
- Em **Aula da grade que vai ao ar com esta gravação**, escolhe "08:30–09:30 · QUÍMICA" na lista.

**Passo 2. Segunda, 26/10: gravação**
- O diretor de imagem faz o relatório da gravação.
- O relatório já vem com "Gravação antecipada · pedido da SEDUC · chamado 18097", sem ninguém digitar.

**Passo 3. Quarta, 28/10: a aula vai ao ar**
- O relatório do assistente e o do diretor dessa aula já mostram: **"📼 Exibição da aula gravada em 26/10/2026 — pedido da SEDUC"**.
- Ninguém precisa informar o professor de novo nem lembrar da data da gravação: o chefe já ligou isso na Agenda.

**Resultado na planilha (Faturamento SEDUC)**

| Dia | LANÇAMENTO | COBRAR (estúdio) |
|---|---|---|
| 26/10 | Gravação antecipada | **Sim** (pedido da SEDUC) |
| 28/10 | Exibição de aula antecipada | **Sim** |

→ O uso de estúdio é cobrado **duas vezes**.

---

## 3. Situação 2: a mesma aula, mas pedida pelo Canal Educação ou pelo professor

Mesmo fluxo da situação 1. A única diferença: na Agenda, o chefe marca **Não — Canal Educação / professor (cobra só a exibição)**, e o chamado não é obrigatório.

| Dia | LANÇAMENTO | COBRAR (estúdio) |
|---|---|---|
| 26/10 | Gravação antecipada | **Não** (cobra só a exibição) |
| 28/10 | Exibição de aula antecipada | **Sim** |

→ O uso de estúdio é cobrado **uma vez só**, na exibição. Se o estúdio der problema no dia da exibição, o professor não é prejudicado, porque a gravação está registrada e ligada.

---

## 4. Situação 3: reposição (o professor faltou)

> A aula de Química de **terça, 27/10**, não aconteceu porque o professor faltou. Ela foi gravada/transmitida depois, em **03/11**.

- **Em 27/10:** o diretor de imagem registra que o professor faltou e o estúdio ficou sem uso. O assistente não faz relatório nesse dia.
- **Em 03/11:** o assistente abre a aula de **27/10** na grade. Essa é a data que vai no **nome do arquivo**. No campo **Data real da gravação**, ele informa **03/11**.
- O sistema monta sozinho o aviso: "Gravação por reposição/falta, referente à aula do dia 27/10/2026 — entra no mês de 11/2026".

| Data da aula (nome do arquivo) | Data da gravação | Mês de faturamento | COBRAR |
|---|---|---|---|
| 27/10/2026 | 03/11/2026 | **11/2026** | **Sim** |

→ **Reposição entra no mês em que aconteceu de fato** (novembro). A antecipada fica no mês de cada dia.

---

## 5. O que fica bloqueado nos relatórios

O que vem da grade horária e da Agenda é preenchido automaticamente e **não pode ser alterado** no relatório (sem aviso na tela: o campo só não aceita edição).

| Campo | Assistente | Diretor de imagem |
|---|---|---|
| Data da aula | 🔒 | 🔒 |
| Turno | 🔒 | 🔒 |
| Turma | 🔒 | 🔒 |
| Disciplina | 🔒 | 🔒 |
| Horário da aula | 🔒 | 🔒 |
| Estúdio do dia (inclusive remanejado) | 🔒 | 🔒 |
| Canal IPTV | 🔒 só leitura | 🔒 vem da Agenda; vazio se o chefe não informou; livre só em evento pedido pela SEDUC |
| Diretor escalado | não aparece (vem da escala) | 🔒 |
| Link do YouTube / chave | 🔒 quando o chefe informou (só copiar) | 🔒 quando o chefe informou (só copiar) |
| Pedido da SEDUC / chamado | não existe mais (fica na Agenda) | não existe mais (fica na Agenda) |
| **Professor** | **aberto** (pode haver substituição) | **aberto** |

---

## 6. Outras regras ligadas a isso

- **Vídeo corrompido:**
  - Enquanto o diretor marcar "vídeo corrompido = Sim", o sistema não busca o link do vídeo e o chefe não consegue validar o relatório.
  - O diretor recupera o vídeo (ou baixa do YouTube, corta e coloca na pasta), desmarca e salva. Aí a busca começa.
- **Coordenação:** só valida o relatório da aula quando o **link do vídeo e o do PDF** já foram coletados.
- **Coleta dos links:** vale o tipo do arquivo no Drive (qualquer vídeo / PDF), e não a extensão ".mp4" ou ".pdf" no nome.

---

## 7. O que ainda precisa da sua confirmação

1. **A marcação SEDUC só aparece em "Gravação antecipada" e "Evento".** Você comentou de uma caixinha "SEDUC" ao lado do nº do chamado em **qualquer agendamento**.
   - Deve valer também para reposição, regravação, aula extra e curso técnico?
   - Curso técnico hoje é cobrado sempre, sem marcação.
2. **No relatório do assistente, o campo virou "Antecipação de aula? Sim/Não".** Você falou em o assistente escolher **Reposição / Antecipada**. Fazemos essa troca?
   - Com "Reposição", apareceria a data da transmissão/gravação, inclusive para reposição **transmitida ao vivo** (hoje a data só aparece em gravação).
3. **Pagamento do professor:** hoje a planilha mostra a cobrança do estúdio (COBRAR). Incluímos uma coluna **PAGA_PROFESSOR**?
   - Sim na transmissão/exibição e na reposição.
   - Não na linha da gravação antecipada, para não pagar o professor duas vezes.
4. **"Se está agendado, cobra":** hoje a planilha é montada a partir dos **relatórios** (assistente + diretor). Um agendamento **sem relatório** não aparece. A cobrança deve partir da **Agenda**, ou basta um alerta de "agendado sem relatório"?
5. **Evento pedido pela SEDUC:** hoje cobra **uma vez** (a transmissão). Está certo?
