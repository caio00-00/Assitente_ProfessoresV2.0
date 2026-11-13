-- Diagnóstico READ-ONLY: relatórios de imagem ocultos ou consolidados
-- Execute no psql/pgAdmin. Não altera dados até você rodar a seção RESTAURAR.

-- 1) Total por status de exclusão
SELECT is_deleted, COUNT(*) AS total
FROM image_director_reports
GROUP BY is_deleted
ORDER BY is_deleted;

-- 2) Relatórios soft-deleted que ainda têm aulas (candidatos a restauração manual)
SELECT r.id, r.data_relatorio, r.turno, r.estudio, r.created_at,
       COUNT(l.id) AS aulas
FROM image_director_reports r
LEFT JOIN image_director_lessons l ON l.report_id = r.id
WHERE r.is_deleted = true
GROUP BY r.id, r.data_relatorio, r.turno, r.estudio, r.created_at
ORDER BY r.data_relatorio DESC;

-- 3) Relatórios ativos visíveis na listagem
SELECT r.id, r.data_relatorio, r.turno, r.estudio, COUNT(l.id) AS aulas
FROM image_director_reports r
LEFT JOIN image_director_lessons l ON l.report_id = r.id
WHERE r.is_deleted = false
GROUP BY r.id, r.data_relatorio, r.turno, r.estudio
ORDER BY r.data_relatorio DESC;

-- RESTAURAR (somente se confirmar que o relatório foi oculto indevidamente):
-- UPDATE image_director_reports SET is_deleted = false WHERE id = '<UUID>';
