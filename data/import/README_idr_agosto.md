# Importação IDR — Agosto/2026 (HML)

## Viabilidade

**Sim, é possível** povoar o HML com relatórios do Diretor de Imagem a partir dos `.txt` do Drive, cruzados com o Excel de auditoria (aba Assistente).

| Métrica | Valor |
|---------|------:|
| Relatórios assistente no Excel (ago/2026) | 2082 |
| Arquivos `.txt` parseados (ago/2026) | 545 |
| Registros IDR gerados | 1098 |
| Vinculados a `class_report_id` | 1004 (~91%) |
| Sem match automático | 94 |
| TXT com falha de parse | 148 |

A aba **Diretor Imagem** do Excel exportado está **vazia** — os dados vêm dos `.txt`.

## Arquivos

| Arquivo | Descrição |
|---------|-----------|
| `app/services/idr_txt_parser.py` | Parser dos `.txt` |
| `scripts/build_idr_agosto_import.py` | Gera JSON (rodar localmente) |
| `scripts/import_idr_agosto_hml.py` | Importa no banco (rodar no Dokploy) |
| `data/import/idr_agosto_2026_payload.json` | Payload gerado (~1,4 MB) |
| `data/import/idr_agosto_2026_match_report.md` | Relatório de correspondência |

## Passo 1 — Gerar payload (local, já feito)

```powershell
python scripts/build_idr_agosto_import.py `
  --txt-dir "C:\Users\Canal Educação\Downloads\drive-download-20260907T191949Z-1-001" `
  --excel "C:\Users\Canal Educação\Downloads\relatorios_audit_2026-09-07 (1).xlsx"
```

## Passo 2 — Deploy + import no Dokploy

Após commit/deploy com o JSON em `data/import/`:

```bash
cd /app
python scripts/import_idr_agosto_hml.py --dry-run
python scripts/import_idr_agosto_hml.py --apply
```

## Regras de correspondência

Cada bloco **AULA** do `.txt` é agrupado por disciplina e comparado ao Excel Assistente por:

1. Data + turno + estúdio + disciplina + professor
2. Reforço por link YouTube (quando presente)

Match com score ≥ 12 grava `class_report_id` no IDR.

## Pré-requisitos no HML

- Tabela `diretores_imagem` com nomes compatíveis (ex.: `GILBERTO ROCHA`, `MAYOLLY SENA`)
- Usuário `admin` existente (para `created_by`)
- Relatórios assistente de agosto já no banco (exportados no Excel)

## Observações

- Registros **sem match** ainda podem ser importados (IDR órfão, `class_report_id` nulo).
- Duplicatas (mesmo diretor+data+turno+estúdio+disciplina) são ignoradas.
- Status importado: `VALIDADO`.
- Checklist/perguntas dinâmicas **não** são preenchidos (não existem nos `.txt`).
