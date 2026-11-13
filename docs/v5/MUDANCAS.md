# Canal Educação v5 — mudanças

Branch `refactor/v5`. A ideia central do v5 é **a Aula no centro**: cada aula prevista vira um registro único, e todo o resto (relatório de aula, relatório de imagem, cancelamento na Agenda, cobrança) se pendura nela.

## F1 — Aulas (feito)

### O que mudou para quem usa
- Nova tela **Aulas** (`/aulas`, menu *Aulas → Aulas*). Mostra o dia, a semana ou o mês com todas as aulas previstas e o andamento de cada uma em um só lugar.
  - Filtros: turma, estúdio, busca livre e chips de status (*Prevista, Sem relatório, Em relatório, Devolvida, Aguardando validação, Aguardando imagem, Validada, Cancelada*).
  - Clicar numa aula abre um painel lateral com os 4 passos (Prevista → Relatório → Validação → Imagem), a cobrança, e botões que levam direto para a ação certa: *Fazer o relatório desta aula* (formulário já preenchido), *Abrir/Corrigir relatório*, *Validar*, *Fazer o relatório de imagem do turno* e *Linha do tempo completa*.
  - A lista se atualiza sozinha a cada 90 s.
- Modo **Ao vivo** na mesma tela: um cartão por estúdio com a aula de agora e a próxima.
- **Tela da TV** (`/aulas/agora`): a mesma visão em tela cheia, com relógio, atualizada a cada 30 s.

### Como funciona por dentro
- Tabela nova `aulas`, montada por dia a partir de:
  1. a grade vigente (com cancelamentos e remanejamentos da Agenda e feriados);
  2. gravações e aulas extras marcadas na Agenda para uma turma;
  3. os relatórios de aula do dia (mesma regra de casamento da conferência v4). Relatório sem aula prevista vira uma aula própria. Se a aula sai da grade e já tinha relatório, ela continua lá, marcada como *fora da grade*; nenhum relatório fica sem aula;
  4. o relatório do diretor de imagem (pela aula ligada ou, se não houver, pelo turno e estúdio).
- Tabela `aulas_sincronizacao` guarda uma assinatura por dia. Se nada mudou naquele dia, ele não é recalculado.
- Front: Jinja + **htmx** + **Alpine** (sem build; arquivos em `app/static/vendor`). Os fragmentos HTML ficam em `/parciais/aulas`.
- API: `GET /api/v1/aulas`, `/resumo`, `/agora`, `/{id}` e `POST /api/v1/aulas/sincronizar` (admin, gestor, coordenação e diretor-chefe). Período máximo de 62 dias. A rota v4 `/api/v1/aulas/linha-do-tempo` continua funcionando.
- Migração Alembic `v5a1b2c3d4e5` (idempotente). O `db_bootstrap` aplica sozinho no Docker e na Vercel (`/api/v1/sistema/migrar`).

### Nada foi removido
As telas v4 continuam iguais. A remoção das telas antigas fica para a F6, depois que você aprovar a lista de cortes.

### Testes
`tests/test_v5_aulas.py`: 26 casos (status, geração pela grade e pela Agenda, ligação dos relatórios, aula fora da grade, relatório de imagem, API, permissões e telas). Suíte completa: 365 passando.

## Próximas fases
F2 relatório de aula em 3 passos · F3 relatório de imagem por turno · F4 Planejamento · F5 Faturamento (com teste de equivalência v4×v5) · F6 Cadastros e remoção das telas antigas · F0 limpeza · F7 entrega.
