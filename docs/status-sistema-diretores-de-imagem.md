# Sistema dos diretores de imagem — status em 09/10/2026

Tudo o que está abaixo está no branch `hml`. A ida para produção (`prd`) está marcada para **segunda-feira à tarde (Rafael)**, depois dos testes de Rafael e Adelino.

## 1. O que está pronto em HML

| # | Entrega | Commit |
|---|---|---|
| 1 | Agenda de Estúdios: agenda do dia por estúdio, conferência com os relatórios, exportação em Excel | `3b61b71`, `cdc8fc2` |
| 2 | Relatório do diretor de imagem com opção **Evento** (sem turma: departamento, horário, chamado) | `b6c8da1` |
| 3 | Pontos de atualização: grade em quadro, disciplinas só da grade da turma, substituto sem o titular, filtro de turmas ativas | `567421b`, `8cacbbc` |
| 4 | Agenda completa do diretor-chefe: remanejamento com destino por aula (nenhuma aula sem estúdio), feriado, sob demanda, observações com TomTicket, 2 diretores por turno, estúdio fixo, prioridade de evento e Libras, arrastar e soltar, botão direito | `cbcddf5` |
| 5 | **Estúdio do relatório do assistente vem da Agenda** (travado; aula remanejada já vem com o estúdio de destino) | `cbcddf5` |
| 6 | Pedagógico (gestor, coordenador, auditor) só visualiza a Agenda | `cbcddf5` |
| 7 | Turnos em abas (Manhã / Tarde / Noite / Dia inteiro) | `c9fd49f` |
| 8 | Nº do horário do diretor de imagem pela **tabela oficial** (dia sem a 1ª aula não desloca mais a numeração) | `ccc779c` |
| 9 | Escala de diretores **diária** (sem escala fixa), com "copiar este dia para…" | `12e35ca` |
| 10 | Decisão de 09/10: diretor de imagem **sem acesso** à Agenda (grade igual à do assistente; visão por estúdio só do diretor-chefe) | a commitar (ver item 3.1) |

Testes automáticos: suíte completa com 191 passando. As 15 falhas que aparecem já existiam antes destas mudanças (`test_report_slot_duplicity`, `test_ficheiro_duplicado`, `test_report_reprocess`, `test_audit_stats_professor`, `test_image_director_finalize::test_list_reports_filter_transmissao_ou_gravada`).

Tutorial de uso para a equipe: documento "Tutorial — Agenda de Estúdios e novidades do sistema".

## 2. Impacto em banco, Docker e Consolidado

- **Docker / deploy:** nada mudou (`Dockerfile`, `docker-compose.yml`, `entrypoint.sh`, `requirements.txt`, Alembic).
- **Banco:** 7 tabelas novas, todas `agenda_*`, criadas sozinhas na inicialização (`create_all` + `garantir_colunas_agenda`). Nenhuma tabela existente teve a estrutura alterada. Única escrita em tabela antiga: "Fixar na grade" muda `grades.estudio_id` (ação manual do diretor-chefe).
- **Consolidado (faturamento):** `app/services/audit_export.py` e as rotas de exportação **não mudaram**. O que muda é o dado que chega:
  - estúdio do relatório do assistente passa a vir da Agenda, no mesmo formato de nome do cadastro de estúdios (o pareamento compara esse texto);
  - relatórios do diretor com origem `evento` aparecem como linha própria, sem turma, "Vinculado: Não".

### Rotas da API para o batimento com o sistema de faturamento (Mairton)

| Rota | Mudança |
|---|---|
| Exportação de auditoria / Consolidado | Nenhuma |
| `GET /api/v1/reports/lookup/disciplinas` | Aceita `?turma_id=` opcional; sem ele, igual a antes |
| `POST/PUT /api/v1/image-director/...` | Aceita `origem = "evento"`; demais origens com as mesmas regras |
| `GET /api/v1/image-director/lookup/horarios` e `lookup/numero-aula` | Mesmo formato; o número agora segue a tabela oficial |
| `/api/v1/agenda-estudios/*` | Rotas novas |
| API externa (Estudologia) | Nenhuma |

## 3. Pendências

### 3.1 Para fazer antes de segunda

1. **Commitar a decisão de 09/10** (diretor de imagem sem acesso à Agenda). Os arquivos já estão alterados na máquina do Caio:
   ```powershell
   git add -A
   git commit -m "fix(agenda): diretor de imagem sem acesso a Agenda (grade igual a do assistente)"
   git push origin hml
   ```
2. **Conferir os vídeos do João Delmiro (exportação de horários).** O problema relatado pelo diretor do Estúdio 6 (sexta 09/10: 3º horário saindo 10:50–11:50 e o 4º indo para a tarde) foi corrigido no commit `ccc779c`. Falta assistir aos vídeos e confirmar se mostram o mesmo problema ou outro.
3. **Corrigir os relatórios já salvos com o horário errado.** O horário fica gravado no relatório, então a correção só vale ao salvar de novo:
   - sexta 09/10, Estúdio 6 (Felipe): reabrir o 3º e o 4º horário e salvar de novo; no "JD Pensamento Computacional", trocar "1º Horário" para **"2º Horário"** antes de salvar;
   - outros dias com a primeira aula faltando podem ter o mesmo problema. Dá para gerar uma lista para conferência (ainda não feita).
4. **Testes de Rafael e Adelino em HML** (roteiro):
   - diretor-chefe: montar a escala do dia e copiar para os próximos dias; marcar evento em cima de aula e escolher o destino; arrastar uma aula para outro estúdio; marcar e desmarcar feriado;
   - assistente: relatório novo de uma aula remanejada → estúdio travado com o de destino;
   - diretor de imagem: dia sem a 1ª aula → lista de horários começando no 2º; "3º Horário" com o horário certo; menu sem a Agenda;
   - gestor/coordenador: Agenda em modo consulta;
   - **Consolidado** do mesmo período em `prd` e `hml`: mesmo número de "Vinculado: Sim"; linhas novas só de origem `evento`.
5. **Batimento das rotas do faturamento** (Paulo): usar a tabela da seção 2.

### 3.2 No deploy de segunda (Rafael)

1. `git fetch` e conferir que `prd` não recebeu nada por fora (`git log origin/hml..origin/prd` deve vir vazio).
2. Subir: `git push origin hml:prd`. O `fix/pontos-atualizacao` vai junto, porque já está no `hml`.
3. Conferir no log de inicialização que a API subiu sem erro (as tabelas `agenda_*` são criadas nesse momento).
4. Em produção, o diretor-chefe precisa cadastrar do zero, porque nada do que foi feito em HML passa para produção: escala do dia (copiando para a semana), horários trancados e sob demanda, feriados, Libras e prioridade de evento.

### 3.3 Depois (não entra na segunda)

| Item | Origem |
|---|---|
| Usabilidade do formulário de agendamento (muita informação na tela) | Reunião 09/10 (Rafael) |
| Unificar Consolidado em uma planilha só (manter as separadas também) | Reunião 09/10 |
| Pedagógico solicitar horário pela Agenda (hoje só visualiza) | Reunião anterior |
| Confirmar com Paulo: canal SEDUC segue o curso ou o estúdio | Reunião com Rafael |
| Evento movido não devolve sozinho as aulas que ele tinha remanejado | Limitação conhecida |
| Relatório do diretor de imagem do tipo Evento: decidir se entra no pagamento | Faturamento |
