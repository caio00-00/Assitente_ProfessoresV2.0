# Revisão de Exportação: Excel (Auditoria v3.4)

Este documento descreve a exportação combinada do painel de auditoria: um único workbook `.xlsx` com **3 abas**, respeitando os mesmos filtros da tela (sem paginação).

---

## Implementação

| Componente | Arquivo |
|------------|---------|
| Rota HTTP | `GET /api/v1/reports/export` em `app/api/rotas_report.py` |
| Serviço | `app/services/audit_export.py` — `build_audit_workbook()` |
| UI | `app/templates/reports_audit.html` — botão **Exportar Excel** |

Nome do arquivo gerado: `relatorios_audit_YYYY-MM-DD.xlsx`.

---

## Abas do workbook

### 1. Consolidado

Visão cruzada assistente ↔ diretor de imagem. Colunas principais:

- Identificação do slot: DATA, DIA, TURNO, ESTÚDIO, CURSO, HORÁRIO, DISCIPLINA, PROFESSOR
- IDs: `ID_RELATORIO_ASSISTENTE`, `ID_RELATORIO_IMAGEM`
- Vínculo: `VINCULADO` (Sim/Não), `ORIGEM_IDR`
- Status e links de ambos os lados (YouTube, vídeo, Vimeo, slide, ficheiro)
- Flags operacionais: atraso, substituição, problema material, vídeo corrompido, áudio, interrupções

**Regra de join** (mesma lógica do painel audit):

1. `class_report_id` explícito no IDR
2. Fallback por slot: data, estúdio, turma, disciplina, horário compatível
3. Fallback por YouTube + diretor + professor

Relatórios órfãos (só assistente ou só IDR) aparecem com `VINCULADO = Não`.

### 2. Assistente

Detalhe completo do Relatório de Aula (~43 colunas), incluindo campos v3.0/v3.1:

- Colunas legadas do export anterior (DATA, TURNO, links Drive, validação, etc.)
- `TIPO DE AULA`, `CONTEÚDO MINISTRADO`, `BNCC / HABILIDADES`, `STATUS COMPLIANCE`, `OBSERVAÇÕES GERAIS`, `MATERIAIS COM PROBLEMA`
- `ID_RELATORIO_IMAGEM` quando houver par

### 3. Diretor Imagem

Detalhe completo do IDR, **uma linha por aula** (`ImageDirectorLesson`):

- Cabeçalho: data, turno, estúdio, professor, horários entrada/saída, YouTube, status, validação
- Detalhe técnico da aula: transmissão/gravada, vídeo corrompido, áudio, vinhetas, créditos
- Colunas dinâmicas: checklist ativo + perguntas extras ativas (cadastro do Diretor-Chefe)

---

## Filtros aplicados

Os query params de `/export` espelham o painel de auditoria:

| Param | Efeito |
|-------|--------|
| `data_aula`, `data_inicio`, `data_fim` | Período |
| `turma_id`, `professor_id`, `disciplina_id` | Slot |
| `status` | Status do relatório |
| `estudio`, `tipo_aula` | Contexto operacional |
| `com_atraso`, `com_substituicao`, `com_problema`, `precisa_correcao` | Pills do audit |
| `created_by` | Autor (assistente) |

**Não** são enviados `limit`, `offset`, `sort_by` ou `sort_order` na exportação.

Filtros de IDR (`ImageDirectorReport`) seguem data, turma, professor, disciplina, status, estúdio e `precisa_correcao`.

---

## Cenários de validação

1. Par assistente+IDR com `class_report_id` → Consolidado `VINCULADO=Sim`
2. Par por slot (sem FK) → Consolidado `VINCULADO=Sim`
3. Só assistente → linha com ID assistente, ID imagem vazio
4. Só IDR → linha com ID imagem, ID assistente vazio
5. Filtro de data → apenas registros no período nas 3 abas
6. Checklist/perguntas dinâmicas → colunas extras na aba Diretor Imagem
7. `MATERIAIS COM PROBLEMA` formatado como `[material]: descrição`
8. Download via UI → toast informando as 3 abas

---

## Testes

`tests/test_audit_export.py` — formatação de materiais, join par/órfão, 3 abas e endpoint HTTP.
