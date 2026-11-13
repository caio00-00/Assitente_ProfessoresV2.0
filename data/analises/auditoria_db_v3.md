# Auditoria de Banco de Dados: Migração v3.0

Esta auditoria tem como objetivo verificar se os modelos principais do SQLAlchemy (em `app/models/`) refletem adequadamente os requisitos de negócio e relacionamentos (ForeignKeys) solicitados para a versão 3.0, com foco nas informações transversais das Aulas, Escolas e Diretor de Imagem.

---

## 🏗️ 1. Estrutura Atual das Tabelas Auditadas

### 👨‍🏫 Tabela **Professor** (`app/models/auxiliares.py`)
* **Modelo**: `Professor`
* **Campos Principais**: `id` UUID, `nome` String(255).
* **Relacionamentos**: Possui a tabela associativa M:N `ProfessorDisciplina` para vinculá-lo a múltiplas disciplinas e possui uma relação 1:N forte de Chave Estrangeira (`professor_id`) mapeada em relatórios de Aulas, funcionando de forma saudável.

### 🎥 Tabela **Aula** (`app/models/class_report.py`)
* **Modelo**: `ClassReport`
* **Campos Principais**: `data_aula`, `horario_aula`, `disciplina_id`, `professor_id`, etc.
* **Campos V3.0 (Recém Integrados)**: `start_time` Time, `end_time` Time.

### 🏫 Tabela **Escola** (`app/models/turma.py`)
* **Modelo**: Em vez de 'Escola', o sistema implementa as raízes educacionais como `Turma` e `Unit` (Unidade/Escola).
* **Campos de Vínculo na Aula**: O modelo `ClassReport` salva os identificadores da turma primária na coluna `turma_id` via PostgreSQL ForeignKey. Foi adicionado um campo secundário chamado `escolas_participantes` como JSON. Não existe uma coluna `escola_id` específica.

### 🎬 Tabela **DiretorImagem** (`scripts/etl_diretores.py`)
* **Modelo**: `DiretorImagem` (definido no ETL, *mas ausente* no pacote oficial `app/models/`).
* **Campos Principais**: `id` Integer, `nome` String(unique).
* **Relacionamento**: Inexistente de forma forte ou nativa (não é importado pela injeção global da aplicação).

---

## 🔍 2. Verificação de Colunas e ForeignKeys V3.0

1. **`youtube_link`**:
   * **Status**: ✅ **EXISTE**
   * **Detalhes**: Criado como `Column(String(1000), nullable=True)` no modelo `ClassReport`. Não exige chave estrangeira, está perfeitamente tipado para receber links/URLs extensas.

2. **`escola_id`**:
   * **Status**: ❌ **NÃO EXISTE**
   * **Detalhes**: A estrutura histórica usa `turma_id` que relaciona-se com a model `Turma`. Para as escolas agregadas/convidadas via V3.0, a coluna criada foi o array `escolas_participantes` (JSONB) sem amarração relacional (ForeignKey). Se a intenção em v3.0 fosse forçar um relacionamento rígido 1:N nomeado `escola_id`, este ainda está pendente.

3. **`diretor_imagem_id`**:
   * **Status**: ❌ **NÃO EXISTE**
   * **Detalhes**: No modelo `ClassReport`, o campo criado no banco e na classe chama-se apenas `diretor_imagem` (`String(255)`). Ele aloca o dado como "texto solto", não como um identificador (UUID ou INT). Sendo assim, **não existe ForeignKey** apontando o relatório de aula para a nova tabela `diretores_imagem` concebida no ETL.

---

## 🚦 3. Conclusão Final

### **Status da Migração V3.0:** <span style="color:red">**PENDENTE**</span>

**Justificativa:** 
Para que o backend e os metadados do banco suportem integralmente os pilares relacionais, precisaremos **refatorar as classes SQLAlchemy**. O `diretor_imagem` está como String quando deveria ser modificado para `diretor_imagem_id` => `ForeignKey("diretores_imagem.id")`. Ademais, esclarecer e modelar melhor o requisito de `escola_id` (se deveria ser inserido um vínculo formal na Unit ou continuar em formato JSONB temporário de fallback) também ditará as adequações. O esquema relacional ainda não encadeou as novas tabelas corretamente.
