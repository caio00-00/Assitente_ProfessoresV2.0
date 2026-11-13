# 📋 Backlog de Tarefas - Agent de Desenvolvimento

> **Instrução Principal:** Você está indo bem, mas tem algumas coisas a resolver. Pense, analise, resolva, analise a estrutura.

---

### 🐛 1. Autenticação e Conta
- [ ] **Resolver erro 500 em "Confirmar Conta"**
  - **Cenário:** Admin cria token para nova conta -> Usuário acessa "Confirmar Conta" -> Insere o token recebido e nova senha -> Pressiona Enter.
  - **Erro retornado:** Quebra com erro 500. A requisição devolve `Unexpected token 'I', "Internal S"... is not valid JSON`.
  - **Ação Exigida:** Identificar o que está causando o *Internal Server Error* no backend que está sendo retornado como texto puro em vez de JSON, e corrigir o fluxo.

### 🎨 2 e 3. Frontend e Responsividade
- [ ] **Tornar a tela "Live monitor" responsiva.**
- [ ] **Tornar todo o Frontend responsivo.**
  - **Ação Exigida:** Adequar todas as telas para todos os tipos de telas e resoluções.
  - ⚠️ **Regra Estrita:** Não alterar absolutamente NADA de lógica ou regra de negócio no frontend, apenas questões de layout e responsividade.

### 📧 4. Integração de E-mail
- [ ] **Corrigir função de envio de e-mails.**
  - **Cenário:** Credenciais já estão no `.env`. Admin cria conta e insere informações.
  - **Falso Positivo:** O sistema exibe mensagem de sucesso na tela. Os logs mostram status `200` (sinal verde).
  - **Problema:** O e-mail real não chega na caixa de entrada do destinatário (apenas o token aparece na tela do admin).
  - **Ação Exigida:** Testar e debugar o serviço de disparo de e-mails, garantindo que o e-mail seja efetivamente entregue.

### 🗄️ 5. Banco de Dados (Database)
- [ ] **Inserção de "Diretores de Imagem" no DB.**
  - **Ação Exigida:** Realizar a inserção no banco de dados seguindo o mesmo padrão dos arquivos já existentes na pasta `/Scripts`.
  - 📍 **Fonte dos dados:** O arquivo de planilha está em - `[C:\Users\joao.borges\Downloads\asssitentes_professores\diretores de imagem.xlsx]`. Ingestão dos diretores de imagem e Lembrando de atualizar o relatório com as informações, campos na parte de fazer relatorio e campos, em relação a diretores de imagem.

### 👨‍🏫 6. Lógica de Professores e Relatórios
- [ ] **Remover duplicidade de Professores:** Garantir que professores apareçam sem duplicatas nos campos específicos.
- [ ] **Corrigir erro de Professor Externo:** - **Cenário:** Ao adicionar "Nome do Professor Externo (Não Cadastrado)".
  - **Erro:** Retorna "Professor não encontrado".
- [ ] **Auditoria de Relatórios:**
  - Verificar e garantir que o relatório está sendo salvo corretamente no banco.
  - Verificar e garantir que estes dados estão sendo registrados corretamente no relatório final.

### 📝 7. Ajustes nos Campos do Formulário
- [ ] **Corrigir validação do campo "Professor(a)":** Sistema acusa que o campo não foi preenchido, mas o usuário preencheu mais de uma vez os professores no campo "Professor Substituto".
- [ ] **Remover campo:** Excluir o campo `"Observações sobre Turno Manhã (Opcional)"`.
- [ ] **Nova funcionalidade na Substituição:** Quando a opção `"Houve Substituição?"` for marcada, disponibilizar uma opção/campo livre para o usuário digitar o nome de um professor que **não** esteja na lista padrão.