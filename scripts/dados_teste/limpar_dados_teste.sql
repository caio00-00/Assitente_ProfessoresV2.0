-- ════════════════════════════════════════════════════════════════════
--  Canal Educação v4 — APAGA os dados de teste criados por dados_teste.sql
--  Só remove o que aquele script criou (pelos ids e pelos e-mails .teste@teste.local).
--  Supabase → SQL Editor → cole tudo → Run.
-- ════════════════════════════════════════════════════════════════════
BEGIN;

-- histórico e relatórios feitos pelos usuários de teste (inclusive os criados durante os testes)
DELETE FROM report_versions WHERE alterado_por IN (SELECT id FROM users WHERE email LIKE '%.teste@teste.local');
DELETE FROM image_director_lessons WHERE report_id IN (
    SELECT id FROM image_director_reports WHERE created_by IN (SELECT id FROM users WHERE email LIKE '%.teste@teste.local'));
DELETE FROM image_director_checklist_responses WHERE report_id IN (
    SELECT id FROM image_director_reports WHERE created_by IN (SELECT id FROM users WHERE email LIKE '%.teste@teste.local'));
DELETE FROM image_director_custom_answers WHERE report_id IN (
    SELECT id FROM image_director_reports WHERE created_by IN (SELECT id FROM users WHERE email LIKE '%.teste@teste.local'));
DELETE FROM image_director_reports WHERE created_by IN (SELECT id FROM users WHERE email LIKE '%.teste@teste.local');
DELETE FROM class_reports WHERE created_by IN (SELECT id FROM users WHERE email LIKE '%.teste@teste.local');

-- cadastros de teste
DELETE FROM grades WHERE versao = 'Grade de teste' OR turma_id IN ('58be6b8b-9eca-51ed-b07d-734671832b49', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3');
DELETE FROM professor_disciplinas WHERE professor_id IN ('67464e47-16e4-5880-bb31-d2d4a1fb8c4c', 'bb8c7563-6678-54a4-85ab-600e852287e9', '3dd45bbb-c110-5f1a-b619-3583483aab6d', '723e5697-aa1c-53e4-8240-38581a855f31');
DELETE FROM professores WHERE id IN ('67464e47-16e4-5880-bb31-d2d4a1fb8c4c', 'bb8c7563-6678-54a4-85ab-600e852287e9', '3dd45bbb-c110-5f1a-b619-3583483aab6d', '723e5697-aa1c-53e4-8240-38581a855f31');
DELETE FROM disciplinas WHERE id IN ('7d6f662e-7e6e-53ca-bc4a-ea3befdb7ca3', 'aead3b62-ee5f-5537-9f9e-635397cd82c7', 'f8b76358-5a6a-5ae8-8681-4e2866bb9a73', '8066b112-3848-5a21-a386-f6e63dc96250');
DELETE FROM turmas WHERE id IN ('58be6b8b-9eca-51ed-b07d-734671832b49', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3');
DELETE FROM estudio e WHERE e.nome IN ('Estúdio Teste 1', 'Estúdio Teste 2')
  AND NOT EXISTS (SELECT 1 FROM grades g WHERE g.estudio_id = e.id);
DELETE FROM diretores_imagem WHERE id IN ('ade98879-2b66-54f0-9379-e9a22ced1a35', 'deb2f978-8c7f-5de2-aba4-e610019bbfbd');

-- usuários de teste (e o rastro deles)
DELETE FROM audit_logs WHERE actor_id IN (SELECT id FROM users WHERE email LIKE '%.teste@teste.local')
   OR target_user_id IN (SELECT id FROM users WHERE email LIKE '%.teste@teste.local');
DELETE FROM login_attempts WHERE email LIKE '%.teste@teste.local';
DELETE FROM users WHERE email LIKE '%.teste@teste.local';

COMMIT;

SELECT 'usuários de teste restantes' AS item, count(*) FROM users WHERE email LIKE '%.teste@teste.local';
