-- ════════════════════════════════════════════════════════════════════
--  Canal Educação v4 — anonimização dos dados de HML para teste local
--
--  Roda DENTRO do banco local depois do pg_restore. Nunca rode isto no
--  banco de HML ou de produção: o script aborta se encontrar sinais de
--  que não está num banco local (veja a trava abaixo).
--
--  O que faz:
--    users              e-mail <papel>NNN@teste.local, nome "<Papel> NNN",
--                       senha Teste@123 para todos, convites/reset apagados
--    professores        "Professor NNNN" (o mesmo nome é aplicado nas
--                       cópias de texto: aulas do diretor, professor externo)
--    diretores_imagem   "Diretor de imagem NN" (e o usuário ligado recebe
--                       o mesmo nome)
--    agenda             autor_nome / criado_por_nome / responsavel_evento
--    audit_logs, login_attempts, report_versions  esvaziadas (guardam
--                       e-mails, IPs e cópias completas dos relatórios)
--
--  Turmas, disciplinas, grade, datas, status, links e textos das aulas
--  ficam como estão: são o que o teste precisa.
-- ════════════════════════════════════════════════════════════════════

\set ON_ERROR_STOP on

DO $$
BEGIN
    IF current_database() NOT IN ('canal_local', 'canal_hml_local')
       AND current_setting('canal.permitir_anonimizar', true) IS DISTINCT FROM 'sim' THEN
        RAISE EXCEPTION 'Banco "%" não parece local. Para rodar mesmo assim: SET canal.permitir_anonimizar = ''sim'';', current_database();
    END IF;
END $$;

BEGIN;

-- Ajuda: só mexe em coluna/tabela que existe (o dump de HML pode ser de uma versão anterior)
CREATE OR REPLACE FUNCTION pg_temp.tem_coluna(t text, c text) RETURNS boolean LANGUAGE sql AS $$
    SELECT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = t AND column_name = c)
$$;

-- ─── Usuários ────────────────────────────────────────────────────────
CREATE TEMP TABLE mapa_usuario AS
SELECT id,
       role,
       full_name AS nome_antigo,
       row_number() OVER (PARTITION BY role ORDER BY created_at NULLS LAST, id) AS n
FROM users;

UPDATE users u SET
    email           = CASE WHEN m.role = 'admin' AND m.n = 1 THEN 'admin@teste.local'
                           ELSE lower(regexp_replace(m.role, '[^a-zA-Z_]', '', 'g')) || lpad(m.n::text, 3, '0') || '@teste.local' END,
    full_name       = initcap(replace(m.role, '_', ' ')) || ' ' || lpad(m.n::text, 3, '0'),
    hashed_password = '$2b$12$IYEUF0iySj8duat5xMdNCuUjd.auWI2EDsHMTgcJzP0lXOdSXFIiK',  -- Teste@123
    email_confirmed = true,
    invite_token    = NULL,
    reset_token     = NULL,
    reset_token_expires_at = NULL
FROM mapa_usuario m
WHERE m.id = u.id;

-- ─── Diretores de imagem ─────────────────────────────────────────────
CREATE TEMP TABLE mapa_diretor AS
SELECT id, nome AS nome_antigo,
       'Diretor de imagem ' || lpad(row_number() OVER (ORDER BY nome, id)::text, 2, '0') AS nome_novo
FROM diretores_imagem;

UPDATE diretores_imagem d SET nome = m.nome_novo FROM mapa_diretor m WHERE m.id = d.id;
UPDATE users u SET full_name = d.nome FROM diretores_imagem d WHERE d.user_id = u.id;

-- ─── Professores (e as cópias do nome em texto) ──────────────────────
CREATE TEMP TABLE mapa_professor AS
SELECT id, nome AS nome_antigo, upper(trim(nome)) AS chave,
       'Professor ' || lpad(row_number() OVER (ORDER BY nome, id)::text, 4, '0') AS nome_novo
FROM professores;

UPDATE professores p SET nome = m.nome_novo FROM mapa_professor m WHERE m.id = p.id;

DO $$
BEGIN
    IF to_regclass('public.image_director_lessons') IS NOT NULL THEN
        UPDATE image_director_lessons l SET professor_nome = COALESCE(
            (SELECT m.nome_novo FROM mapa_professor m WHERE m.chave = upper(trim(l.professor_nome)) LIMIT 1),
            'Professor externo')
        WHERE l.professor_nome IS NOT NULL AND l.professor_nome <> '';
    END IF;

    IF pg_temp.tem_coluna('class_reports', 'professor_nome_externo') THEN
        UPDATE class_reports SET professor_nome_externo = 'Professor externo'
        WHERE professor_nome_externo IS NOT NULL AND professor_nome_externo <> '';
    END IF;
    IF pg_temp.tem_coluna('class_reports', 'professor_substituto_nome_externo') THEN
        UPDATE class_reports SET professor_substituto_nome_externo = 'Professor substituto externo'
        WHERE professor_substituto_nome_externo IS NOT NULL AND professor_substituto_nome_externo <> '';
    END IF;
    IF pg_temp.tem_coluna('image_director_reports', 'professor_nome_externo') THEN
        UPDATE image_director_reports SET professor_nome_externo = 'Professor externo'
        WHERE professor_nome_externo IS NOT NULL AND professor_nome_externo <> '';
    END IF;

    -- ─── Agenda de estúdios ──────────────────────────────────────────
    IF pg_temp.tem_coluna('agenda_observacoes', 'autor_nome') THEN
        UPDATE agenda_observacoes o SET autor_nome = COALESCE(
            (SELECT u.full_name FROM users u WHERE u.id = o.autor_id), 'Usuário')
        WHERE o.autor_nome IS NOT NULL;
    END IF;
    IF pg_temp.tem_coluna('agenda_intervalos', 'criado_por_nome') THEN
        UPDATE agenda_intervalos i SET criado_por_nome = COALESCE(
            (SELECT u.full_name FROM users u WHERE u.id = i.criado_por), 'Usuário')
        WHERE i.criado_por_nome IS NOT NULL;
    END IF;
    IF pg_temp.tem_coluna('agenda_agendamentos', 'responsavel_evento') THEN
        UPDATE agenda_agendamentos SET responsavel_evento = 'Responsável do evento'
        WHERE responsavel_evento IS NOT NULL AND responsavel_evento <> '';
    END IF;

    -- ─── Tabelas de rastro (e-mails, IPs, cópias completas) ──────────
    IF to_regclass('public.audit_logs') IS NOT NULL THEN TRUNCATE audit_logs; END IF;
    IF to_regclass('public.login_attempts') IS NOT NULL THEN TRUNCATE login_attempts; END IF;
    IF to_regclass('public.report_versions') IS NOT NULL THEN TRUNCATE report_versions; END IF;
END $$;

-- ─── Conferência: nada de e-mail real pode sobrar ────────────────────
DO $$
DECLARE sobrou int;
BEGIN
    SELECT count(*) INTO sobrou FROM users WHERE email NOT LIKE '%@teste.local';
    IF sobrou > 0 THEN
        RAISE EXCEPTION 'Anonimização incompleta: % usuário(s) com e-mail real.', sobrou;
    END IF;
END $$;

COMMIT;

-- Resumo para o terminal
SELECT role AS papel, count(*) AS usuarios, min(email) AS exemplo_de_login
FROM users GROUP BY role ORDER BY role;
