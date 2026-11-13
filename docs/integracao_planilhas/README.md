# Integração Planilhas Cursos Técnicos ↔ Assistente

Preenche as planilhas do Drive ("PLANILHAS CURSOS TECNICOS") com os dados do
banco do Assistente (PRD), por disciplina.

## Como funciona
- Cada planilha do Drive = um curso técnico. Cada **aba** = uma **disciplina**.
- Cada aba tem 4 colunas: `NOME ARQUIVO | LINK VÍDEO (VIMEO) | LINK VÍDEO (DRIVE) | LINK PDF`.
- Um **Apps Script** (instalado na planilha) percorre as abas; para cada uma
  manda o nome da aba ao endpoint do Assistente e escreve as linhas retornadas.
- Botão sob demanda: menu **🔄 Assistente → Atualizar todas as abas**.

## Endpoint (Assistente, somente leitura, auth `X-API-Key`)
```
GET /api/v1/external/aulas-por-disciplina?disciplina=<nome da aba>
→ { "disciplina_consultada": "...",
    "disciplina_casada": "ANÁLISE QUÍMICA DOS ALIMENTOS" | null,
    "total": 12,
    "linhas": [ {"nome_arquivo": "...", "vimeo_url": "...", "drive_url": "...", "pdf_url": "..."} ] }
```
- **Casamento da disciplina:** normalizado (acento/caixa/separadores). Exato
  primeiro; fallback por prefixo. Se não casar → `disciplina_casada: null, total: 0`.
- **Linhas:** relatórios finalizados (com `nome_ficheiro_gerado`) da disciplina,
  ordenados por data. Colunas = `nome_ficheiro_gerado`, `vimeo_link`,
  `video_link` (Drive), `slide_link` (PDF).

## Instalação do Apps Script
Ver cabeçalho de [`apps_script.gs`](./apps_script.gs). Resumo:
1. Planilha → Extensões → Apps Script → cole o `apps_script.gs`.
2. Propriedades do script: `X_API_KEY = <EXTERNAL_API_KEY do Assistente>`.
3. Recarregue a planilha → menu **🔄 Assistente**.

## Observações
- Os campos VIMEO/DRIVE/PDF aparecem conforme já existirem no relatório (o Vimeo
  é preenchido pela integração Drive→Vimeo; Drive/PDF pela sincronização de
  compliance). Disciplinas sem aulas no banco ficam com a aba só com cabeçalho.
- Disciplinas cuja aba não casa exatamente podem precisar de ajuste de nome
  (alias) — o endpoint reporta `disciplina_casada: null` para essas.
- Reescreve a aba inteira a cada execução (full sync, sem duplicar).
