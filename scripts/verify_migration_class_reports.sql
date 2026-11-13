-- Verificação READ-ONLY antes/depois da migração e4f6a8b0c2d3
-- Não altera dados. Execute no psql ou pgAdmin.

-- 1) Contagem total (deve ser IGUAL antes e depois)
SELECT COUNT(*) AS total_relatorios FROM class_reports;
SELECT COUNT(*) AS total_nao_deletados FROM class_reports WHERE is_deleted = false;

-- 2) Colunas v3.1 ausentes? (se retornar linhas, a migração ainda é necessária)
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'class_reports'
  AND column_name IN (
    'precisa_correcao',
    'observacao_coordenacao',
    'validado_por',
    'validado_em'
  );

-- Esperado ANTES da migração: 0 linhas (nenhuma coluna existe)
-- Esperado DEPOIS da migração: 4 linhas

-- 3) Tamanho atual da coluna status
SELECT character_maximum_length
FROM information_schema.columns
WHERE table_name = 'class_reports' AND column_name = 'status';

-- 4) Distribuição de status (conferir que nada mudou depois)
SELECT status, COUNT(*) AS qtd
FROM class_reports
GROUP BY status
ORDER BY qtd DESC;

-- 5) Revisão Alembic aplicada
SELECT version_num FROM alembic_version;
