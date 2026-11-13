📋 Documento de Orientação: Canal Educação v3.0
Este documento detalha as atualizações necessárias para o fluxo de relatórios, monitoramento ao vivo e gestão de grade horária.

1. O QUE PRECISA SER CRIADO (Novas Implementações)
A. Estrutura de Escolas Participantes
Tabela/Relacionamento: Criar uma nova entidade ReportSchool ou um campo JSONB no modelo ClassReport para armazenar a lista dinâmica de escolas.

Interface: Componente de "Input + Tag" no frontend, onde o assistente digita o nome da escola, clica em "Adicionar" e a escola aparece em uma lista (chips) antes do envio.

B. Motor de Verificação de Choque (Clash Detection)
Lógica de Back-end: Criar um serviço de validação que impeça a criação/agendamento de uma aula se já houver outra aula no mesmo estudio OU no mesmo canal\_iptv dentro do intervalo de tempo selecionado.

Query de Interseção: $(inicio_A < fim_B) \text{ AND } (fim_A > inicio_B)$. Todos os campos de tempo para esta comparação devem utilizar obrigatoriamente o formato $(HH:MM:SS)$ [HORA:MINUTOS:SEGUNDOS].

C. Seção de Observações de Turno (Manhã)
Modelo: Criar uma entidade de ShiftObservation ou campo específico para consolidação de ocorrências pedagógicas/técnicas exclusivas do turno da manhã.

D. Detalhamento de Problemas por Material (Recursos e Materiais)
Lógica: Abaixo do campo "Problema com Material", deve ser criado um fluxo dinâmico:

Seletor de Material: Um dropdown que lista os materiais disponíveis (baseado na lista de Recursos e Materiais já existente no formulário).

Campo de Descrição do Problema: Um campo de texto que só se torna visível após um material ser selecionado, para que o assistente informe o tipo de defeito ou problema técnico ocorrido.

2. O QUE PRECISA SER ALTERADO (Refatoração)
A. Modelo de Dados (ClassReport)
Adição dos seguintes campos:

diretor_imagem (String, Obrigatório).

youtube_link (URL, Obrigatório).

ticket_number (String, Obrigatório se regular=Não).

needs_editing (Boolean, Default=False).

start_time e end_time (Time/DateTime, Obrigatórios para aulas avulsas).

problematic_materials (JSONB): Para armazenar o material selecionado e a descrição do problema vinculado.

B. Lógica Condicional do Formulário
Estado Reativo: * Se regular == "Não" -> Exibir campos de Número do Chamado, Necessidade de Edição e Horário Customizado.

Se Problema com Material == "Sim" -> Exibir o Seletor de Material e, sequencialmente, o campo de Descrição do Problema.

C. Live Monitor (Painel de Controle)
Alterar a query do monitor para incluir registros onde is_avulsa=True. Atualmente, o monitor foca na grade semanal; ele deve passar a olhar para a tabela de relatórios em tempo real.

D. Grade Horária (Filtros e Persistência)
Filtro por Estúdio: Adicionar filtro studio_id. Ao selecionar um estúdio, a grade deve recarregar apenas as disciplinas vinculadas àquele espaço físico.

Persistência de Seleção (UX): Implementar persistência de estado para a "Turma Selecionada". Ao navegar entre a grade e o formulário de relatório, ou ao clicar em "← Voltar à Grade", o sistema deve manter a última turma selecionada ativa na seção, evitando que o usuário precise selecioná-la novamente.

3. DIFICULDADES ENVOLVIDAS E DESAFIOS TÉCNICOS
Cálculo de Conflitos na Persistência: Validar choque de horário na tentativa de salvar o formulário. O sistema deve retornar um erro claro indicando qual estúdio ou canal está em conflito.

Flexibilidade de Horário: A opção de "Selecionar pelo horário ou pelo período" exige que o back-end normalize os dados para o formato de slots que o Live Monitor entende.

Integridade do Relatório: Validar se o link do YouTube é uma URL válida e impedir a finalização caso um problema de material tenha sido marcado mas não descrito.

Gerenciamento de Estado Global: A persistence da turma selecionada exige o uso de localStorage ou estado global no frontend.

4. ANÁLISE DE IMPACTO, RISCOS E SOLUÇÕES (Advisor)
⚠️ Impacto no Banco de Dados
Risco: Migração de campos obrigatórios invalida relatórios antigos.

Solução: Executar migração via Alembic aplicando o valor "Não Informado" para registros existentes.

Risco: Relacionamento de Escolas como texto simples suja a base de dados.

Solução: Criar tabela mestre de Escolas com Autocomplete no formulário.

⚠️ Problemas Operacionais
Risco: A Trava de Conflitos impede o lançamento de aulas reais devido a erros na grade oficial.

Solução: Botão de "Forçar Registro" (Bypass) exclusivo para perfis Gestor/Admin com justificativa obrigatória.

Risco: Link do YouTube indisponível no início da aula.

Solução: Permitir salvamento parcial, mas bloquear a Finalização do relatório sem o link.

5. INTEGRAÇÃO NO RELATÓRIO FINAL (Saída de Dados)
Todas as alterações de entrada devem ser refletidas nas interfaces de visualização e exportação:

Visualização Web (Dashboard do Gestor):

Incluir colunas para Diretor de Imagem, Link do YouTube (clicável) e Escolas Participantes.

Destacar visualmente relatórios que possuam Problemas com Materiais, exibindo qual equipamento falhou e a descrição do erro.

Exportação (Excel/PDF):

Adicionar as novas colunas e formatar o campo de problemas técnicos como: [Nome do Material]: [Descrição do Problema].

Garantir que as Observações do Turno Manhã apareçam no consolidado diário.

Formatos de horário devem manter o padrão $(HH:MM:SS)$.