# Relatório de povoamento — Diretores de Imagem (HML)

Gerado a partir do payload `idr_agosto_2026_payload.json` e cadastro `data/diretores_imagem.csv`.

## Resumo

| Métrica | Valor |
|---------|------:|
| Diretores distintos (agosto) | **24** |
| Relatórios IDR referenciados | **1032** |
| E-mails fictícios gerados | **24** |
| Domínio | `hml.oroshub.local` |

## Tipos de correspondência nome TXT → cadastro

- **primeiro_nome**: 16
- **alias**: 4
- **alias_sem_csv**: 3
- **exato**: 1

## Tabela de povoamento

| Nome cadastro | Nome no TXT | E-mail fictício | Rel. ago | Match |
|---------------|-------------|-----------------|--------:|-------|
| ECILMAR MONTEIRO DE BRITO SILVA | ECILMAR | `ecilmar.monteiro.de.brito.silva@hml.oroshub.local` | 80 | primeiro_nome |
| ANTONIO NILTOMAR DE ANDRADE | NILTOMAR ANDRADE | `antonio.niltomar.de.andrade@hml.oroshub.local` | 77 | primeiro_nome |
| JACKSON ONORIO DANIEL | JACKSON DANIEL | `jackson.onorio.daniel@hml.oroshub.local` | 75 | primeiro_nome |
| THIAGO DA CONCEICAO SOUSA | THIAGO SOUSA | `thiago.da.conceicao.sousa@hml.oroshub.local` | 74 | primeiro_nome |
| DANIEL FONSECA DA SILVA NASCIMENTO | DANIEL DA SILVA | `daniel.fonseca.da.silva.nascimento@hml.oroshub.local` | 67 | alias |
| ADAYLTON SANTIAGO PORTELA E SILVA | SANTYAGO | `adaylton.santiago.portela.e.silva@hml.oroshub.local` | 64 | alias |
| JOSÉ RIBAMAR FEITOSA DO NASCIMENTO JUNIOR | JUNIOR FEITOSA | `jose.ribamar.feitosa.do.nascimento.junior@hml.oroshub.local` | 60 | alias |
| ESTENIO OLIVEIRA PAZ | ESTENIO PAZ | `estenio.oliveira.paz@hml.oroshub.local` | 59 | primeiro_nome |
| FLAVILTON DA SILVA MOURAO | FLAVILTON MOURÃO | `flavilton.da.silva.mourao@hml.oroshub.local` | 59 | primeiro_nome |
| KHALIL SAREV LOPES VERA CRUZ | KHALIL | `khalil.sarev.lopes.vera.cruz@hml.oroshub.local` | 57 | primeiro_nome |
| GILBERTO RODRIGUES DA ROCHA | GILBERTO ROCHA | `gilberto.rodrigues.da.rocha@hml.oroshub.local` | 54 | primeiro_nome |
| FABRICIO BATISTA | FABRICIO BATISTA | `fabricio.batista@hml.oroshub.local` | 43 | alias_sem_csv |
| MAYOLLY SENA DA ROCHA | MAYOLLY | `mayolly.sena.da.rocha@hml.oroshub.local` | 42 | primeiro_nome |
| JAILSON BARBOSA DA CUNHA | JAILSON | `jailson.barbosa.da.cunha@hml.oroshub.local` | 41 | primeiro_nome |
| OCIONEIDE DE SOUSA | OCIONEIDE DE SOUSA | `ocioneide.de.sousa@hml.oroshub.local` | 39 | exato |
| FELIPE CARVALHO COSTA | FELIPE CARVALHO | `felipe.carvalho.costa@hml.oroshub.local` | 38 | primeiro_nome |
| RENAN MESQUITA DE MELO SILVA | RENAN MESQUITA | `renan.mesquita.de.melo.silva@hml.oroshub.local` | 22 | primeiro_nome |
| PAULO CESAR | PAULO CESAR | `paulo.cesar@hml.oroshub.local` | 20 | alias_sem_csv |
| MARIANA BARBOSA DE SOUSA | MARIANA BARBOSA | `mariana.barbosa.de.sousa@hml.oroshub.local` | 16 | primeiro_nome |
| BRUNO | BRUNO | `bruno@hml.oroshub.local` | 12 | alias_sem_csv |
| PABLLO ROOSVELLT DOS SANTOS LOBO | PABLLO LOBO | `pabllo.roosvellt.dos.santos.lobo@hml.oroshub.local` | 11 | primeiro_nome |
| ISAEL DAVID DA SILVA MELO | ISAEL MELO | `isael.david.da.silva.melo@hml.oroshub.local` | 9 | primeiro_nome |
| ANDERSON VITOR DOS SANTOS | ANDERSON VITOR | `anderson.vitor.dos.santos@hml.oroshub.local` | 8 | primeiro_nome |
| ANTONIO GONCALVES FERREIRA JUNIOR | ANTONIO JR | `antonio.goncalves.ferreira.junior@hml.oroshub.local` | 5 | alias |

## Atenção — revisar manualmente

- **FABRICIO BATISTA** → `FABRICIO BATISTA` (alias_sem_csv)
- **PAULO CESAR** → `PAULO CESAR` (alias_sem_csv)
- **BRUNO** → `BRUNO` (alias_sem_csv)

## Arquivos gerados

- CSV: `data/import/diretores_imagem_povoamento.csv`
- Este relatório: `data/import/relatorio_povoamento_diretores_imagem.md`

## Próximo passo (Dokploy)

Após revisar este relatório:

```bash
cd /app
python scripts/seed_diretores_imagem_hml.py --dry-run
python scripts/seed_diretores_imagem_hml.py --apply
python scripts/import_idr_agosto_hml.py --apply
```

**Nota:** e-mails são fictícios (`@hml.oroshub.local`), senha inicial sugerida `Trocar@123`.