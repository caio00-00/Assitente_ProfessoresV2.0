-- ════════════════════════════════════════════════════════════════════
--  Canal Educação v4 — DADOS DE TESTE para o Supabase (SQL Editor)
--
--  Como usar: Supabase → SQL Editor → New query → cole TUDO → Run.
--  Antes, as tabelas precisam existir (rota /api/v1/sistema/migrar, ou o
--  Docker já ter subido uma vez apontando para este banco).
--
--  Pode rodar mais de uma vez: o que já existe é pulado (ON CONFLICT).
--  As datas são relativas a hoje (current_date), então os dados sempre
--  aparecem no Início, que mostra as aulas recentes.
--  Para apagar tudo isto: limpar_dados_teste.sql (não mexe em mais nada).
--
--  TODOS os usuários entram com a senha:  Teste@123
--
--  admin.teste@teste.local          Administrador
--  gestor.teste@teste.local         Gestor
--  coordenacao.teste@teste.local    Coordenação (valida relatórios de aula)
--  auditor.teste@teste.local        Auditoria (só leitura)
--  assistente1.teste@teste.local    Assistente — tem rascunho, devolvido, validado…
--  assistente2.teste@teste.local    Assistente — relatórios esperando o Drive
--  assistente3.teste@teste.local    Assistente — cancelado e vermelho
--  diretor1.teste@teste.local       Diretor de imagem
--  diretor2.teste@teste.local       Diretor de imagem — devolvido e vídeo corrompido
--  chefe.teste@teste.local          Diretor-chefe (valida relatórios de imagem)
-- ════════════════════════════════════════════════════════════════════

BEGIN;
-- ─── Usuários ───
INSERT INTO users (id, email, hashed_password, full_name, is_active, role, email_confirmed, theme_preference, created_at, updated_at) VALUES
  ('8abe272e-c456-5484-99c0-de1fbdad58f1', 'admin.teste@teste.local', '$2b$12$IYEUF0iySj8duat5xMdNCuUjd.auWI2EDsHMTgcJzP0lXOdSXFIiK', 'Ana Admin (teste)', true, 'admin', true, 'dark', now(), now()),
  ('671622b1-398c-56ae-bb25-2049f5adf99b', 'gestor.teste@teste.local', '$2b$12$IYEUF0iySj8duat5xMdNCuUjd.auWI2EDsHMTgcJzP0lXOdSXFIiK', 'Gustavo Gestor (teste)', true, 'gestor', true, 'dark', now(), now()),
  ('043967a3-d89b-5967-9cf9-fda7cd2971ce', 'coordenacao.teste@teste.local', '$2b$12$IYEUF0iySj8duat5xMdNCuUjd.auWI2EDsHMTgcJzP0lXOdSXFIiK', 'Carla Coordenação (teste)', true, 'coordenador', true, 'dark', now(), now()),
  ('6bf555e0-2801-59f5-9c89-88abc3720194', 'auditor.teste@teste.local', '$2b$12$IYEUF0iySj8duat5xMdNCuUjd.auWI2EDsHMTgcJzP0lXOdSXFIiK', 'Otávio Auditor (teste)', true, 'auditor', true, 'dark', now(), now()),
  ('3c00696b-962b-5a32-9d23-f52aa4b5f067', 'assistente1.teste@teste.local', '$2b$12$IYEUF0iySj8duat5xMdNCuUjd.auWI2EDsHMTgcJzP0lXOdSXFIiK', 'Bruno Assistente (teste)', true, 'assistente', true, 'dark', now(), now()),
  ('39981cb1-9610-5985-bb02-490d82575cda', 'assistente2.teste@teste.local', '$2b$12$IYEUF0iySj8duat5xMdNCuUjd.auWI2EDsHMTgcJzP0lXOdSXFIiK', 'Júlia Assistente (teste)', true, 'assistente', true, 'dark', now(), now()),
  ('b817bc88-25ca-535c-a1ac-170a2a8d6ad3', 'assistente3.teste@teste.local', '$2b$12$IYEUF0iySj8duat5xMdNCuUjd.auWI2EDsHMTgcJzP0lXOdSXFIiK', 'Rafael Assistente (teste)', true, 'assistente', true, 'dark', now(), now()),
  ('a86121b1-0e56-5d24-972b-8ced47c686ea', 'diretor1.teste@teste.local', '$2b$12$IYEUF0iySj8duat5xMdNCuUjd.auWI2EDsHMTgcJzP0lXOdSXFIiK', 'Diego Diretor (teste)', true, 'diretor_imagem', true, 'dark', now(), now()),
  ('4b4ad87c-aa40-5efe-96c8-c5e470fea31e', 'diretor2.teste@teste.local', '$2b$12$IYEUF0iySj8duat5xMdNCuUjd.auWI2EDsHMTgcJzP0lXOdSXFIiK', 'Lara Diretora (teste)', true, 'diretor_imagem', true, 'dark', now(), now()),
  ('54a46c1a-a744-5939-91cc-cc653e70024b', 'chefe.teste@teste.local', '$2b$12$IYEUF0iySj8duat5xMdNCuUjd.auWI2EDsHMTgcJzP0lXOdSXFIiK', 'Helena Diretora-chefe (teste)', true, 'diretor_chefe', true, 'dark', now(), now())
ON CONFLICT DO NOTHING;

-- ─── Diretores de imagem (ligados aos usuários) ───
INSERT INTO diretores_imagem (id, nome, is_active, user_id) VALUES
  ('ade98879-2b66-54f0-9379-e9a22ced1a35', 'DIEGO DIRETOR (TESTE)', true, 'a86121b1-0e56-5d24-972b-8ced47c686ea'),
  ('deb2f978-8c7f-5de2-aba4-e610019bbfbd', 'LARA DIRETORA (TESTE)', true, '4b4ad87c-aa40-5efe-96c8-c5e470fea31e')
ON CONFLICT DO NOTHING;

-- ─── Professores e disciplinas ───
INSERT INTO professores (id, nome, is_active) VALUES
  ('67464e47-16e4-5880-bb31-d2d4a1fb8c4c', 'ANA LIMA (TESTE)', true),
  ('bb8c7563-6678-54a4-85ab-600e852287e9', 'CARLOS SOUZA (TESTE)', true),
  ('3dd45bbb-c110-5f1a-b619-3583483aab6d', 'MARIA ROCHA (TESTE)', true),
  ('723e5697-aa1c-53e4-8240-38581a855f31', 'PEDRO ALVES (TESTE)', true)
ON CONFLICT DO NOTHING;
INSERT INTO disciplinas (id, nome, is_active) VALUES
  ('7d6f662e-7e6e-53ca-bc4a-ea3befdb7ca3', 'MATEMÁTICA (TESTE)', true),
  ('aead3b62-ee5f-5537-9f9e-635397cd82c7', 'LÍNGUA PORTUGUESA (TESTE)', true),
  ('f8b76358-5a6a-5ae8-8681-4e2866bb9a73', 'HISTÓRIA (TESTE)', true),
  ('8066b112-3848-5a21-a386-f6e63dc96250', 'FÍSICA (TESTE)', true)
ON CONFLICT DO NOTHING;
INSERT INTO professor_disciplinas (id, professor_id, disciplina_id) VALUES
  ('c3469f82-a628-591d-9f5b-84e699d8519c', '67464e47-16e4-5880-bb31-d2d4a1fb8c4c', '7d6f662e-7e6e-53ca-bc4a-ea3befdb7ca3'),
  ('9577a51b-ed9d-57b0-8614-ba8faf28081a', 'bb8c7563-6678-54a4-85ab-600e852287e9', 'aead3b62-ee5f-5537-9f9e-635397cd82c7'),
  ('4b710a1f-525a-59d3-b19e-8e72d0dd63d8', '3dd45bbb-c110-5f1a-b619-3583483aab6d', 'f8b76358-5a6a-5ae8-8681-4e2866bb9a73'),
  ('b5f2913c-d919-5ce9-a387-03244720d3fe', '723e5697-aa1c-53e4-8240-38581a855f31', '8066b112-3848-5a21-a386-f6e63dc96250')
ON CONFLICT DO NOTHING;

-- ─── Turmas ───
INSERT INTO turmas (id, nome, modalidade, serie_modulo, turno, is_active) VALUES
  ('58be6b8b-9eca-51ed-b07d-734671832b49', 'TESTE 1ª SÉRIE A', 'REGULAR', '1ª Série', 'MANHÃ', true),
  ('ccdf7083-8c45-52a3-9db7-aa8fc813aae3', 'TESTE 2ª SÉRIE B', 'REGULAR', '2ª Série', 'TARDE', true)
ON CONFLICT DO NOTHING;

-- ─── Estúdios (id numérico: só cria se ainda não existir um com o mesmo nome) ───
INSERT INTO estudio (nome, horario_inicio, horario_fim, funciona_24h, ativo, data_criacao)
SELECT v.nome, '07:00', '22:00', false, true, now()
FROM (VALUES ('Estúdio Teste 1'), ('Estúdio Teste 2')) AS v(nome)
WHERE NOT EXISTS (SELECT 1 FROM estudio e WHERE e.nome = v.nome);

-- ─── Grade horária (segunda a sexta) ───
INSERT INTO grades (id, turma_id, disciplina_id, professor_id, estudio_id, tipo_slot, dia_semana, horario_inicio, horario_fim, turno_aula, canal_iptv, versao) VALUES
  ('737621ae-a40c-5646-846c-7c7651380ab8', '58be6b8b-9eca-51ed-b07d-734671832b49', '7d6f662e-7e6e-53ca-bc4a-ea3befdb7ca3', '67464e47-16e4-5880-bb31-d2d4a1fb8c4c', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 1' ORDER BY id LIMIT 1), 'aula', 0, '08:00', '09:00', 'MANHÃ', 1, 'Grade de teste'),
  ('771ebaab-abde-5a59-b1c5-f373ef56d780', '58be6b8b-9eca-51ed-b07d-734671832b49', '7d6f662e-7e6e-53ca-bc4a-ea3befdb7ca3', '67464e47-16e4-5880-bb31-d2d4a1fb8c4c', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 1' ORDER BY id LIMIT 1), 'aula', 1, '08:00', '09:00', 'MANHÃ', 1, 'Grade de teste'),
  ('e1ad0d3d-a259-57fe-8ba2-4153d4ad293e', '58be6b8b-9eca-51ed-b07d-734671832b49', '7d6f662e-7e6e-53ca-bc4a-ea3befdb7ca3', '67464e47-16e4-5880-bb31-d2d4a1fb8c4c', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 1' ORDER BY id LIMIT 1), 'aula', 2, '08:00', '09:00', 'MANHÃ', 1, 'Grade de teste'),
  ('81765a40-3662-5773-b82b-ec7330b38328', '58be6b8b-9eca-51ed-b07d-734671832b49', '7d6f662e-7e6e-53ca-bc4a-ea3befdb7ca3', '67464e47-16e4-5880-bb31-d2d4a1fb8c4c', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 1' ORDER BY id LIMIT 1), 'aula', 3, '08:00', '09:00', 'MANHÃ', 1, 'Grade de teste'),
  ('ae91e664-3acf-5f62-ac87-0240a39255a4', '58be6b8b-9eca-51ed-b07d-734671832b49', '7d6f662e-7e6e-53ca-bc4a-ea3befdb7ca3', '67464e47-16e4-5880-bb31-d2d4a1fb8c4c', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 1' ORDER BY id LIMIT 1), 'aula', 4, '08:00', '09:00', 'MANHÃ', 1, 'Grade de teste'),
  ('d410e2dd-d5ac-5222-abe0-69ea8d194885', '58be6b8b-9eca-51ed-b07d-734671832b49', 'aead3b62-ee5f-5537-9f9e-635397cd82c7', 'bb8c7563-6678-54a4-85ab-600e852287e9', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 1' ORDER BY id LIMIT 1), 'aula', 0, '09:00', '10:00', 'MANHÃ', 1, 'Grade de teste'),
  ('8f1281bc-1206-5f7d-bc11-e30822dfa19e', '58be6b8b-9eca-51ed-b07d-734671832b49', 'aead3b62-ee5f-5537-9f9e-635397cd82c7', 'bb8c7563-6678-54a4-85ab-600e852287e9', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 1' ORDER BY id LIMIT 1), 'aula', 1, '09:00', '10:00', 'MANHÃ', 1, 'Grade de teste'),
  ('98212ead-0766-5b22-95f8-630c3e19ef95', '58be6b8b-9eca-51ed-b07d-734671832b49', 'aead3b62-ee5f-5537-9f9e-635397cd82c7', 'bb8c7563-6678-54a4-85ab-600e852287e9', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 1' ORDER BY id LIMIT 1), 'aula', 2, '09:00', '10:00', 'MANHÃ', 1, 'Grade de teste'),
  ('2abda6b1-4de0-56bd-aa79-305d2d8cbf8e', '58be6b8b-9eca-51ed-b07d-734671832b49', 'aead3b62-ee5f-5537-9f9e-635397cd82c7', 'bb8c7563-6678-54a4-85ab-600e852287e9', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 1' ORDER BY id LIMIT 1), 'aula', 3, '09:00', '10:00', 'MANHÃ', 1, 'Grade de teste'),
  ('9d38b62c-83d5-562d-af82-8049c4c6f382', '58be6b8b-9eca-51ed-b07d-734671832b49', 'aead3b62-ee5f-5537-9f9e-635397cd82c7', 'bb8c7563-6678-54a4-85ab-600e852287e9', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 1' ORDER BY id LIMIT 1), 'aula', 4, '09:00', '10:00', 'MANHÃ', 1, 'Grade de teste'),
  ('736238e3-2daf-5cd7-89bf-f2c54e08b9ab', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', 'f8b76358-5a6a-5ae8-8681-4e2866bb9a73', '3dd45bbb-c110-5f1a-b619-3583483aab6d', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 2' ORDER BY id LIMIT 1), 'aula', 0, '14:00', '15:00', 'TARDE', 2, 'Grade de teste'),
  ('19d09148-051f-51fb-b393-8c55370cc042', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', 'f8b76358-5a6a-5ae8-8681-4e2866bb9a73', '3dd45bbb-c110-5f1a-b619-3583483aab6d', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 2' ORDER BY id LIMIT 1), 'aula', 1, '14:00', '15:00', 'TARDE', 2, 'Grade de teste'),
  ('06ea4999-83b3-5126-8b90-8c2653bce699', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', 'f8b76358-5a6a-5ae8-8681-4e2866bb9a73', '3dd45bbb-c110-5f1a-b619-3583483aab6d', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 2' ORDER BY id LIMIT 1), 'aula', 2, '14:00', '15:00', 'TARDE', 2, 'Grade de teste'),
  ('7b40c3c9-240f-5bc5-b6bc-414ce1b86c7d', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', 'f8b76358-5a6a-5ae8-8681-4e2866bb9a73', '3dd45bbb-c110-5f1a-b619-3583483aab6d', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 2' ORDER BY id LIMIT 1), 'aula', 3, '14:00', '15:00', 'TARDE', 2, 'Grade de teste'),
  ('525721c9-46a5-5e70-8160-a11716436e50', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', 'f8b76358-5a6a-5ae8-8681-4e2866bb9a73', '3dd45bbb-c110-5f1a-b619-3583483aab6d', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 2' ORDER BY id LIMIT 1), 'aula', 4, '14:00', '15:00', 'TARDE', 2, 'Grade de teste'),
  ('57afc7cc-1689-536c-9131-fc744220799a', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', '8066b112-3848-5a21-a386-f6e63dc96250', '723e5697-aa1c-53e4-8240-38581a855f31', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 2' ORDER BY id LIMIT 1), 'aula', 0, '15:00', '16:00', 'TARDE', 2, 'Grade de teste'),
  ('19f1452d-2e76-5517-b537-6b23f5528db1', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', '8066b112-3848-5a21-a386-f6e63dc96250', '723e5697-aa1c-53e4-8240-38581a855f31', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 2' ORDER BY id LIMIT 1), 'aula', 1, '15:00', '16:00', 'TARDE', 2, 'Grade de teste'),
  ('b318d301-b251-53e0-af2e-a16ded09e52f', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', '8066b112-3848-5a21-a386-f6e63dc96250', '723e5697-aa1c-53e4-8240-38581a855f31', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 2' ORDER BY id LIMIT 1), 'aula', 2, '15:00', '16:00', 'TARDE', 2, 'Grade de teste'),
  ('fda44ff0-b6b0-58b7-9a35-e9c3fdeae9a8', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', '8066b112-3848-5a21-a386-f6e63dc96250', '723e5697-aa1c-53e4-8240-38581a855f31', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 2' ORDER BY id LIMIT 1), 'aula', 3, '15:00', '16:00', 'TARDE', 2, 'Grade de teste'),
  ('0b304a4d-5a92-57d0-836d-93cfd34a00a9', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', '8066b112-3848-5a21-a386-f6e63dc96250', '723e5697-aa1c-53e4-8240-38581a855f31', (SELECT id FROM estudio WHERE nome = 'Estúdio Teste 2' ORDER BY id LIMIT 1), 'aula', 4, '15:00', '16:00', 'TARDE', 2, 'Grade de teste')
ON CONFLICT DO NOTHING;

-- ─── Relatórios de aula (um de cada situação) ───
INSERT INTO class_reports (id, created_by, created_at, status, data_aula, turno, estudio, turma_id, disciplina_id, professor_id, horario_aula, regular, tipo_aula, canal_utilizado, conteudo_ministrado, interacao_professor_aluno, problema_material, teve_substituicao, teve_atraso, conflito_geminada_resolvido, status_compliance, needs_editing, is_deleted, precisa_correcao, video_link, slide_link, nome_ficheiro_gerado, nome_normalizado, observacao_coordenacao, validado_por, validado_em, justificativa_cancelamento, cancelado_por, cancelado_em, observacoes) VALUES
  ('078dd05e-ef7f-5151-9458-b70e371208f2', '3c00696b-962b-5a32-9d23-f52aa4b5f067', now() - interval '0 days' - interval '4 hours', 'RASCUNHO', (current_date - 0), 'Manhã', 'Estúdio Teste 1', '58be6b8b-9eca-51ed-b07d-734671832b49', '7d6f662e-7e6e-53ca-bc4a-ea3befdb7ca3', '67464e47-16e4-5880-bb31-d2d4a1fb8c4c', '08:00 - 09:00', 'Sim', 'Transmissão ao vivo', '1', 'Equações do 1º grau (rascunho)', 'Sim', 'Não', false, false, false, 'Pendente', false, false, false, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('23ce6cc5-c206-546b-b155-73487a598d10', '3c00696b-962b-5a32-9d23-f52aa4b5f067', now() - interval '1 days' - interval '4 hours', 'RASCUNHO', (current_date - 1), 'Manhã', 'Estúdio Teste 1', '58be6b8b-9eca-51ed-b07d-734671832b49', 'aead3b62-ee5f-5537-9f9e-635397cd82c7', 'bb8c7563-6678-54a4-85ab-600e852287e9', '09:00 - 10:00', 'Sim', 'Transmissão ao vivo', '1', 'Interpretação de texto', 'Sim', 'Não', false, false, false, 'Pendente', false, false, true, NULL, NULL, NULL, NULL, 'O conteúdo ministrado não confere com o plano. Corrija e finalize de novo.', NULL, NULL, NULL, NULL, NULL, NULL),
  ('88d811fb-e68e-54d9-8dfe-162485289f77', '39981cb1-9610-5985-bb02-490d82575cda', now() - interval '1 days' - interval '4 hours', 'AGUARDANDO_VALIDACAO', (current_date - 1), 'Manhã', 'Estúdio Teste 1', '58be6b8b-9eca-51ed-b07d-734671832b49', 'aead3b62-ee5f-5537-9f9e-635397cd82c7', 'bb8c7563-6678-54a4-85ab-600e852287e9', '09:00 - 10:00', 'Sim', 'Transmissão ao vivo', '1', 'Gêneros textuais', 'Sim', 'Não', false, false, false, 'Pendente', false, false, false, NULL, NULL, 'TESTE 1ª SÉRIE A - LÍNGUA PORTUGUESA - ' || to_char(current_date - 1, 'DD.MM.YYYY') || ' - AULA 2', regexp_replace(lower(translate('TESTE 1ª SÉRIE A - LÍNGUA PORTUGUESA - ' || to_char(current_date - 1, 'DD.MM.YYYY') || ' - AULA 2', 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüçªº', 'AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuucao')), '[^a-z0-9]', '', 'g'), NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('55986278-4808-5256-bebb-b23c11b397d2', '39981cb1-9610-5985-bb02-490d82575cda', now() - interval '2 days' - interval '4 hours', 'AGUARDANDO_VALIDACAO', (current_date - 2), 'Tarde', 'Estúdio Teste 2', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', 'f8b76358-5a6a-5ae8-8681-4e2866bb9a73', '3dd45bbb-c110-5f1a-b619-3583483aab6d', '14:00 - 15:00', 'Sim', 'Transmissão ao vivo', '1', 'Revolução Francesa', 'Sim', 'Não', false, false, false, 'Pendente', false, false, false, 'https://drive.google.com/file/d/video-de-teste/view', NULL, 'TESTE 2ª SÉRIE B - HISTÓRIA - ' || to_char(current_date - 2, 'DD.MM.YYYY') || ' - AULA 1', regexp_replace(lower(translate('TESTE 2ª SÉRIE B - HISTÓRIA - ' || to_char(current_date - 2, 'DD.MM.YYYY') || ' - AULA 1', 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüçªº', 'AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuucao')), '[^a-z0-9]', '', 'g'), NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('17c5d6c0-ed31-5c10-bd76-7b28e5086734', '3c00696b-962b-5a32-9d23-f52aa4b5f067', now() - interval '3 days' - interval '4 hours', 'AGUARDANDO_VALIDACAO', (current_date - 3), 'Manhã', 'Estúdio Teste 1', '58be6b8b-9eca-51ed-b07d-734671832b49', '7d6f662e-7e6e-53ca-bc4a-ea3befdb7ca3', '67464e47-16e4-5880-bb31-d2d4a1fb8c4c', '08:00 - 09:00', 'Sim', 'Transmissão ao vivo', '1', 'Funções afins', 'Sim', 'Não', false, false, false, 'Verde', false, false, false, 'https://drive.google.com/file/d/video-de-teste/view', 'https://drive.google.com/file/d/pdf-de-teste/view', 'TESTE 1ª SÉRIE A - MATEMÁTICA - ' || to_char(current_date - 3, 'DD.MM.YYYY') || ' - AULA 1', regexp_replace(lower(translate('TESTE 1ª SÉRIE A - MATEMÁTICA - ' || to_char(current_date - 3, 'DD.MM.YYYY') || ' - AULA 1', 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüçªº', 'AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuucao')), '[^a-z0-9]', '', 'g'), NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('e8b13712-f9c6-5537-9c23-6df2a5805f22', '3c00696b-962b-5a32-9d23-f52aa4b5f067', now() - interval '5 days' - interval '4 hours', 'VALIDADO', (current_date - 5), 'Manhã', 'Estúdio Teste 1', '58be6b8b-9eca-51ed-b07d-734671832b49', '7d6f662e-7e6e-53ca-bc4a-ea3befdb7ca3', '67464e47-16e4-5880-bb31-d2d4a1fb8c4c', '08:00 - 09:00', 'Sim', 'Transmissão ao vivo', '1', 'Conjuntos numéricos', 'Sim', 'Não', false, false, false, 'Verde', false, false, false, 'https://drive.google.com/file/d/video-de-teste/view', 'https://drive.google.com/file/d/pdf-de-teste/view', 'TESTE 1ª SÉRIE A - MATEMÁTICA - ' || to_char(current_date - 5, 'DD.MM.YYYY') || ' - AULA 1', regexp_replace(lower(translate('TESTE 1ª SÉRIE A - MATEMÁTICA - ' || to_char(current_date - 5, 'DD.MM.YYYY') || ' - AULA 1', 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüçªº', 'AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuucao')), '[^a-z0-9]', '', 'g'), NULL, '043967a3-d89b-5967-9cf9-fda7cd2971ce', now() - interval '4 days', NULL, NULL, NULL, NULL),
  ('3cc9f610-04ce-5141-a903-f5f6a4b9821a', 'b817bc88-25ca-535c-a1ac-170a2a8d6ad3', now() - interval '4 days' - interval '4 hours', 'CANCELADO', (current_date - 4), 'Tarde', 'Estúdio Teste 2', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', '8066b112-3848-5a21-a386-f6e63dc96250', '723e5697-aa1c-53e4-8240-38581a855f31', '15:00 - 16:00', 'Sim', 'Transmissão ao vivo', '1', 'Leis de Newton', 'Sim', 'Não', false, false, false, 'Pendente', false, false, false, NULL, NULL, 'TESTE 2ª SÉRIE B - FÍSICA - ' || to_char(current_date - 4, 'DD.MM.YYYY') || ' - AULA 1', regexp_replace(lower(translate('TESTE 2ª SÉRIE B - FÍSICA - ' || to_char(current_date - 4, 'DD.MM.YYYY') || ' - AULA 1', 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüçªº', 'AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuucao')), '[^a-z0-9]', '', 'g'), NULL, NULL, NULL, 'Aula não aconteceu: professor ausente.', 'b817bc88-25ca-535c-a1ac-170a2a8d6ad3', now() - interval '4 days', 'Professor avisou em cima da hora.'),
  ('0b1cb8f7-c70d-523e-9bf9-126856adee5d', 'b817bc88-25ca-535c-a1ac-170a2a8d6ad3', now() - interval '10 days' - interval '4 hours', 'AGUARDANDO_VALIDACAO', (current_date - 10), 'Tarde', 'Estúdio Teste 2', 'ccdf7083-8c45-52a3-9db7-aa8fc813aae3', '8066b112-3848-5a21-a386-f6e63dc96250', '723e5697-aa1c-53e4-8240-38581a855f31', '15:00 - 16:00', 'Sim', 'Transmissão ao vivo', '1', 'Cinemática', 'Sim', 'Não', false, false, false, 'Vermelho', false, false, false, NULL, NULL, 'TESTE 2ª SÉRIE B - FÍSICA - ' || to_char(current_date - 10, 'DD.MM.YYYY') || ' - AULA 1', regexp_replace(lower(translate('TESTE 2ª SÉRIE B - FÍSICA - ' || to_char(current_date - 10, 'DD.MM.YYYY') || ' - AULA 1', 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüçªº', 'AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuucao')), '[^a-z0-9]', '', 'g'), NULL, NULL, NULL, NULL, NULL, NULL, NULL)
ON CONFLICT DO NOTHING;

-- ─── Relatórios de imagem (por turno) ───
INSERT INTO image_director_reports (id, created_by, created_at, status, precisa_correcao, diretor_imagem_id, data_relatorio, turno, estudio, regular, is_deleted, origem, class_report_id, finalized_at, observacao_coordenacao, validado_por, validado_em) VALUES
  ('70acbe28-5ce0-5c7a-90cd-fcad71c7dab3', 'a86121b1-0e56-5d24-972b-8ced47c686ea', now() - interval '3 days' - interval '3 hours', 'AGUARDANDO_VALIDACAO', false, 'ade98879-2b66-54f0-9379-e9a22ced1a35', (current_date - 3), 'Manhã', 'Estúdio Teste 1', 'Sim', false, 'manual', '17c5d6c0-ed31-5c10-bd76-7b28e5086734', now() - interval '3 days' - interval '2 hours', NULL, NULL, NULL),
  ('c3533f7b-c3ca-5ca4-941b-6558ab71170a', 'a86121b1-0e56-5d24-972b-8ced47c686ea', now() - interval '5 days' - interval '3 hours', 'VALIDADO', false, 'ade98879-2b66-54f0-9379-e9a22ced1a35', (current_date - 5), 'Manhã', 'Estúdio Teste 1', 'Sim', false, 'manual', 'e8b13712-f9c6-5537-9c23-6df2a5805f22', now() - interval '5 days' - interval '2 hours', NULL, '54a46c1a-a744-5939-91cc-cc653e70024b', now() - interval '4 days'),
  ('908a667e-4b84-5a80-9f02-9ad74d9b64b4', 'a86121b1-0e56-5d24-972b-8ced47c686ea', now() - interval '0 days' - interval '3 hours', 'RASCUNHO', false, 'ade98879-2b66-54f0-9379-e9a22ced1a35', (current_date - 0), 'Manhã', 'Estúdio Teste 1', 'Sim', false, 'manual', '078dd05e-ef7f-5151-9458-b70e371208f2', NULL, NULL, NULL, NULL),
  ('6d513dbd-1846-5f81-a510-8e8b6ccfbf07', '4b4ad87c-aa40-5efe-96c8-c5e470fea31e', now() - interval '2 days' - interval '3 hours', 'RASCUNHO', true, 'deb2f978-8c7f-5de2-aba4-e610019bbfbd', (current_date - 2), 'Tarde', 'Estúdio Teste 2', 'Sim', false, 'manual', '55986278-4808-5256-bebb-b23c11b397d2', NULL, 'Faltou informar o número do chamado do problema de áudio.', NULL, NULL),
  ('17fbe744-2c9c-5eb8-9506-54ccf74c8cdc', '4b4ad87c-aa40-5efe-96c8-c5e470fea31e', now() - interval '1 days' - interval '3 hours', 'AGUARDANDO_VALIDACAO', false, 'deb2f978-8c7f-5de2-aba4-e610019bbfbd', (current_date - 1), 'Manhã', 'Estúdio Teste 1', 'Sim', false, 'manual', '88d811fb-e68e-54d9-8dfe-162485289f77', now() - interval '1 days' - interval '2 hours', NULL, NULL, NULL)
ON CONFLICT DO NOTHING;
INSERT INTO image_director_lessons (id, report_id, numero_aula, class_report_id, disciplina_nome, professor_nome, canal_utilizado, transmissao_ou_gravada, video_corrompido, interrupcoes, problema_audio, vinhetas_corretas, creditos_corretos, created_at, numero_chamado, video_corrompido_obs) VALUES
  ('5c1e236c-6e2e-5234-8df1-85cbedbf548f', '70acbe28-5ce0-5c7a-90cd-fcad71c7dab3', 1, '17c5d6c0-ed31-5c10-bd76-7b28e5086734', 'MATEMÁTICA (TESTE)', 'ANA LIMA (TESTE)', '1', 'Transmissão', 'Não', 'Não', 'Não', 'Sim', 'Sim', now(), NULL, NULL),
  ('7579f263-ecba-59f3-9225-96b26d3c60e9', '70acbe28-5ce0-5c7a-90cd-fcad71c7dab3', 2, NULL, 'LÍNGUA PORTUGUESA (TESTE)', 'CARLOS SOUZA (TESTE)', '1', 'Transmissão', 'Não', 'Não', 'Não', 'Sim', 'Sim', now(), NULL, NULL),
  ('b368b057-b258-5d77-aa89-70dcc99a0480', 'c3533f7b-c3ca-5ca4-941b-6558ab71170a', 1, 'e8b13712-f9c6-5537-9c23-6df2a5805f22', 'MATEMÁTICA (TESTE)', 'ANA LIMA (TESTE)', '1', 'Transmissão', 'Não', 'Não', 'Não', 'Sim', 'Sim', now(), NULL, NULL),
  ('4ec13b20-17f0-5457-812e-ab5e1ceda449', '908a667e-4b84-5a80-9f02-9ad74d9b64b4', 1, '078dd05e-ef7f-5151-9458-b70e371208f2', 'MATEMÁTICA (TESTE)', 'ANA LIMA (TESTE)', '1', 'Transmissão', 'Não', 'Não', 'Não', 'Sim', 'Sim', now(), NULL, NULL),
  ('5b2ee742-f500-56a2-8b81-759b330433b7', '6d513dbd-1846-5f81-a510-8e8b6ccfbf07', 1, '55986278-4808-5256-bebb-b23c11b397d2', 'HISTÓRIA (TESTE)', 'MARIA ROCHA (TESTE)', '1', 'Transmissão', 'Não', 'Não', 'Sim', 'Sim', 'Sim', now(), NULL, NULL),
  ('8f2d9024-a97a-553f-9f02-487673b206d4', '17fbe744-2c9c-5eb8-9506-54ccf74c8cdc', 2, '88d811fb-e68e-54d9-8dfe-162485289f77', 'LÍNGUA PORTUGUESA (TESTE)', 'CARLOS SOUZA (TESTE)', '1', 'Transmissão', 'Sim', 'Não', 'Não', 'Sim', 'Sim', now(), 'CH-12345', 'Arquivo da gravação chegou com 0 bytes.')
ON CONFLICT DO NOTHING;

COMMIT;

-- ─── Conferência: o que foi criado ───
SELECT 'usuários' AS item, count(*) FROM users WHERE email LIKE '%.teste@teste.local'
UNION ALL SELECT 'relatórios de aula', count(*) FROM class_reports WHERE created_by IN (SELECT id FROM users WHERE email LIKE '%.teste@teste.local')
UNION ALL SELECT 'relatórios de imagem', count(*) FROM image_director_reports WHERE created_by IN (SELECT id FROM users WHERE email LIKE '%.teste@teste.local')
UNION ALL SELECT 'aulas na grade', count(*) FROM grades WHERE versao = 'Grade de teste';

SELECT email AS login, 'Teste@123' AS senha, role AS papel, full_name AS nome
FROM users WHERE email LIKE '%.teste@teste.local' ORDER BY role, email;
