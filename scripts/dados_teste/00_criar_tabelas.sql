-- ════════════════════════════════════════════════════════════════════
--  Canal Educação v4 — CRIA TODAS AS TABELAS (banco vazio)
--
--  Use quando a API ainda não consegue conectar no Supabase para rodar a
--  migração sozinha. Faz exatamente o que /api/v1/sistema/migrar faria num
--  banco vazio: cria as tabelas da v4 e marca o Alembic na versão atual
--  (v4b2c3d4e5f6), então as próximas migrações rodam normalmente.
--
--  Supabase → SQL Editor → New query → cole TUDO → Run.  Rode UMA vez.
--  Depois rode dados_teste.sql para ter usuários e relatórios de teste.
-- ════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    IF to_regclass('public.users') IS NOT NULL THEN
        RAISE EXCEPTION 'As tabelas já existem neste banco (achei public.users). Não precisa rodar este script.';
    END IF;
END $$;

BEGIN;

--
-- PostgreSQL database dump
--

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--


--
-- Name: agenda_agendamentos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agenda_agendamentos (
    id uuid NOT NULL,
    data date NOT NULL,
    estudio_id integer NOT NULL,
    horario_inicio time without time zone NOT NULL,
    horario_fim time without time zone NOT NULL,
    tipo character varying(30) NOT NULL,
    titulo character varying(255) NOT NULL,
    descricao text,
    professor character varying(255),
    turma_id uuid,
    grade_id uuid,
    chamado character varying(50),
    chamado_link character varying(500),
    status character varying(20) NOT NULL,
    canal_iptv_id integer,
    departamento character varying(120),
    chave_transmissao character varying(255),
    nome_evento character varying(255),
    responsavel_evento character varying(255),
    solicitante_antecipacao character varying(20),
    data_referencia date,
    motivo_referencia character varying(255),
    reposicao boolean DEFAULT false NOT NULL,
    grade_exibicao_id uuid,
    criado_por uuid,
    criado_em timestamp without time zone NOT NULL,
    atualizado_por uuid,
    atualizado_em timestamp without time zone NOT NULL
);

--
-- Name: agenda_bloqueios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agenda_bloqueios (
    id integer NOT NULL,
    estudio_id integer NOT NULL,
    dias_semana character varying(20) NOT NULL,
    horario_inicio time without time zone NOT NULL,
    horario_fim time without time zone NOT NULL,
    motivo character varying(255),
    ativo boolean NOT NULL,
    tipo character varying(20) NOT NULL,
    minimo_aulas integer,
    atualizado_por uuid,
    atualizado_em timestamp without time zone NOT NULL
);

--
-- Name: agenda_bloqueios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agenda_bloqueios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: agenda_bloqueios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agenda_bloqueios_id_seq OWNED BY public.agenda_bloqueios.id;

--
-- Name: agenda_escala_dia; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agenda_escala_dia (
    id integer NOT NULL,
    data date NOT NULL,
    turno character varying(10) NOT NULL,
    estudio_id integer NOT NULL,
    diretor_imagem_id uuid,
    diretor2_imagem_id uuid,
    troca_horario time without time zone,
    trocas_json text,
    youtube_link character varying(500),
    chave_transmissao character varying(255),
    observacao character varying(255),
    atualizado_por uuid,
    atualizado_em timestamp without time zone NOT NULL
);

--
-- Name: agenda_escala_dia_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agenda_escala_dia_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: agenda_escala_dia_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agenda_escala_dia_id_seq OWNED BY public.agenda_escala_dia.id;

--
-- Name: agenda_escala_fixa; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agenda_escala_fixa (
    id integer NOT NULL,
    dia_semana integer NOT NULL,
    turno character varying(10) NOT NULL,
    estudio_id integer NOT NULL,
    diretor_imagem_id uuid NOT NULL,
    atualizado_por uuid,
    atualizado_em timestamp without time zone NOT NULL
);

--
-- Name: agenda_escala_fixa_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agenda_escala_fixa_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: agenda_escala_fixa_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agenda_escala_fixa_id_seq OWNED BY public.agenda_escala_fixa.id;

--
-- Name: agenda_estudio_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agenda_estudio_config (
    estudio_id integer NOT NULL,
    libras boolean NOT NULL,
    prioridade_evento integer,
    atualizado_por uuid,
    atualizado_em timestamp without time zone NOT NULL
);

--
-- Name: agenda_feriados; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agenda_feriados (
    id integer NOT NULL,
    data date NOT NULL,
    nome character varying(120) NOT NULL,
    criado_por uuid,
    criado_em timestamp without time zone NOT NULL
);

--
-- Name: agenda_feriados_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agenda_feriados_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: agenda_feriados_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agenda_feriados_id_seq OWNED BY public.agenda_feriados.id;

--
-- Name: agenda_intervalos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agenda_intervalos (
    id integer NOT NULL,
    turno character varying(10) NOT NULL,
    estudio_id integer,
    horario_inicio time without time zone,
    horario_fim time without time zone,
    vigente_desde date NOT NULL,
    vigente_ate date,
    motivo character varying(255),
    criado_por uuid,
    criado_por_nome character varying(255),
    criado_em timestamp without time zone NOT NULL
);

--
-- Name: agenda_intervalos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agenda_intervalos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: agenda_intervalos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agenda_intervalos_id_seq OWNED BY public.agenda_intervalos.id;

--
-- Name: agenda_observacoes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agenda_observacoes (
    id integer NOT NULL,
    data date NOT NULL,
    grade_id uuid,
    agendamento_id uuid,
    texto text NOT NULL,
    link character varying(500),
    autor_id uuid,
    autor_nome character varying(255),
    criado_em timestamp without time zone NOT NULL
);

--
-- Name: agenda_observacoes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agenda_observacoes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: agenda_observacoes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agenda_observacoes_id_seq OWNED BY public.agenda_observacoes.id;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);

--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id uuid NOT NULL,
    actor_id uuid,
    action character varying(50) NOT NULL,
    target_user_id uuid,
    details text,
    created_at timestamp with time zone NOT NULL,
    ip_address character varying(45)
);

--
-- Name: canal_iptv; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.canal_iptv (
    id integer NOT NULL,
    nome character varying(100) NOT NULL,
    numero integer NOT NULL,
    ativo boolean NOT NULL,
    data_criacao timestamp without time zone NOT NULL
);

--
-- Name: canal_iptv_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.canal_iptv_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: canal_iptv_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.canal_iptv_id_seq OWNED BY public.canal_iptv.id;

--
-- Name: class_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.class_reports (
    id uuid NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    status character varying(30) NOT NULL,
    data_aula date NOT NULL,
    turno character varying(20) NOT NULL,
    estudio character varying(50) NOT NULL,
    turma_id uuid NOT NULL,
    disciplina_id uuid NOT NULL,
    professor_id uuid,
    professor_nome_externo character varying(255),
    horario_aula character varying(50) NOT NULL,
    regular character varying(10) NOT NULL,
    tipo_aula character varying(100) NOT NULL,
    canal_utilizado character varying(50) NOT NULL,
    conteudo_ministrado character varying(100) NOT NULL,
    interacao_professor_aluno character varying(50) NOT NULL,
    interacao_outras_desc text,
    atividade_pratica character varying(50),
    observacoes text,
    tipo_recursos_utilizados json,
    recursos_outro_desc text,
    problema_material character varying(50) NOT NULL,
    problema_material_outro_desc text,
    teve_substituicao boolean NOT NULL,
    professor_substituto_id uuid,
    professor_substituto_nome_externo character varying(255),
    teve_atraso boolean NOT NULL,
    minutos_atraso character varying(5),
    observacao_atraso text,
    nome_ficheiro_gerado character varying(500),
    conflito_geminada_resolvido boolean NOT NULL,
    video_link character varying(1000),
    vimeo_link character varying(1000),
    status_compliance character varying(20) NOT NULL,
    md5_checksum character varying(32),
    compliance_verificado_em timestamp with time zone,
    escolas_participantes json,
    diretor_imagem_id uuid,
    youtube_link character varying(1000),
    ticket_number character varying(100),
    needs_editing boolean NOT NULL,
    start_time time without time zone,
    end_time time without time zone,
    problematic_materials json,
    observacoes_manha text,
    bncc_habilidades text,
    slide_link character varying(1000),
    is_deleted boolean DEFAULT false NOT NULL,
    data_execucao_real date,
    data_referencia_aula date,
    solicitante_antecipacao character varying(20),
    motivo_referencia character varying(255),
    precisa_correcao boolean DEFAULT false NOT NULL,
    observacao_coordenacao text,
    validado_por uuid,
    validado_em timestamp with time zone,
    justificativa_cancelamento text,
    cancelado_por uuid,
    cancelado_em timestamp with time zone,
    nome_normalizado character varying(500)
);

--
-- Name: diretores_imagem; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diretores_imagem (
    id uuid NOT NULL,
    nome character varying(255) NOT NULL,
    is_active boolean NOT NULL,
    user_id uuid
);

--
-- Name: disciplinas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.disciplinas (
    id uuid NOT NULL,
    nome character varying(255) NOT NULL,
    nomenclatura_padrao character varying(255),
    is_active boolean NOT NULL
);

--
-- Name: estudio; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.estudio (
    id integer NOT NULL,
    nome character varying(100) NOT NULL,
    horario_inicio time without time zone NOT NULL,
    horario_fim time without time zone NOT NULL,
    funciona_24h boolean NOT NULL,
    ativo boolean NOT NULL,
    data_criacao timestamp without time zone NOT NULL
);

--
-- Name: estudio_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.estudio_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: estudio_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.estudio_id_seq OWNED BY public.estudio.id;

--
-- Name: grade_versao; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grade_versao (
    id integer NOT NULL,
    turma_id uuid NOT NULL,
    is_active boolean NOT NULL,
    data_ativacao timestamp without time zone,
    data_criacao timestamp without time zone NOT NULL,
    criado_por uuid
);

--
-- Name: grade_versao_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.grade_versao_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: grade_versao_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.grade_versao_id_seq OWNED BY public.grade_versao.id;

--
-- Name: grades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grades (
    id uuid NOT NULL,
    turma_id uuid,
    disciplina_id uuid,
    professor_id uuid,
    grade_versao_id integer,
    slot_horario_id integer,
    estudio_id integer,
    canal_iptv_id integer,
    tipo_slot character varying(20) NOT NULL,
    dia_semana integer NOT NULL,
    horario_inicio time without time zone NOT NULL,
    horario_fim time without time zone NOT NULL,
    turno_aula character varying(20),
    canal_iptv integer,
    descricao character varying(255),
    vigencia_inicio date,
    vigencia_fim date,
    versao character varying(50)
);

--
-- Name: image_director_checklist_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.image_director_checklist_items (
    id uuid NOT NULL,
    nome character varying(255) NOT NULL,
    ativo boolean NOT NULL,
    ordem integer NOT NULL,
    created_at timestamp with time zone NOT NULL
);

--
-- Name: image_director_checklist_responses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.image_director_checklist_responses (
    id uuid NOT NULL,
    report_id uuid NOT NULL,
    item_id uuid NOT NULL,
    resposta boolean
);

--
-- Name: image_director_custom_answers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.image_director_custom_answers (
    id uuid NOT NULL,
    question_id uuid NOT NULL,
    report_id uuid,
    lesson_id uuid,
    resposta_texto text,
    resposta_bool boolean
);

--
-- Name: image_director_custom_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.image_director_custom_questions (
    id uuid NOT NULL,
    texto text NOT NULL,
    tipo character varying(20) NOT NULL,
    nivel character varying(20) NOT NULL,
    obrigatoria boolean NOT NULL,
    ativa boolean NOT NULL,
    ordem integer NOT NULL,
    created_by uuid,
    created_at timestamp with time zone NOT NULL
);

--
-- Name: image_director_lessons; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.image_director_lessons (
    id uuid NOT NULL,
    report_id uuid NOT NULL,
    numero_aula integer NOT NULL,
    class_report_id uuid,
    disciplina_nome character varying(255) NOT NULL,
    professor_nome character varying(255) NOT NULL,
    canal_utilizado character varying(50),
    transmissao_ou_gravada character varying(20) NOT NULL,
    video_corrompido character varying(10) NOT NULL,
    video_corrompido_obs text,
    interrupcoes character varying(10) NOT NULL,
    problema_audio character varying(10) NOT NULL,
    problema_audio_obs text,
    vinhetas_corretas character varying(10) NOT NULL,
    vinhetas_corretas_obs text,
    creditos_corretos character varying(10) NOT NULL,
    observacoes text,
    numero_chamado character varying(32),
    created_at timestamp with time zone NOT NULL
);

--
-- Name: image_director_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.image_director_reports (
    id uuid NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    status character varying(20) NOT NULL,
    finalized_at timestamp with time zone,
    precisa_correcao boolean DEFAULT false NOT NULL,
    observacao_coordenacao text,
    validado_por uuid,
    validado_em timestamp with time zone,
    diretor_imagem_id uuid NOT NULL,
    data_relatorio date NOT NULL,
    turno character varying(20) NOT NULL,
    estudio character varying(50) NOT NULL,
    turma_id uuid,
    serie_modulo_manual character varying(255),
    disciplina_id uuid,
    disciplina_nome character varying(255),
    professor_id uuid,
    professor_nome_externo character varying(255),
    horario_aula character varying(100),
    regular character varying(10) DEFAULT 'Sim'::character varying NOT NULL,
    ticket_number character varying(100),
    start_time time without time zone,
    end_time time without time zone,
    horario_entrada time without time zone,
    horario_saida time without time zone,
    youtube_link character varying(1000),
    chave_transmissao character varying(255),
    nome_evento character varying(255),
    departamento_solicitante character varying(120),
    responsavel_evento character varying(255),
    solicitante_antecipacao character varying(20),
    data_referencia date,
    motivo_referencia character varying(255),
    observacoes_gerais text,
    is_deleted boolean DEFAULT false NOT NULL,
    class_report_id uuid,
    origem character varying(30) DEFAULT 'grade'::character varying NOT NULL,
    justificativa_cancelamento text,
    cancelado_por uuid,
    cancelado_em timestamp with time zone
);

--
-- Name: login_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.login_attempts (
    id integer NOT NULL,
    email character varying(255) NOT NULL,
    ip character varying(64),
    sucesso character varying(1) NOT NULL,
    criado_em timestamp with time zone NOT NULL
);

--
-- Name: login_attempts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.login_attempts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: login_attempts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.login_attempts_id_seq OWNED BY public.login_attempts.id;

--
-- Name: professor_disciplinas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.professor_disciplinas (
    id uuid NOT NULL,
    professor_id uuid NOT NULL,
    disciplina_id uuid NOT NULL
);

--
-- Name: professores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.professores (
    id uuid NOT NULL,
    nome character varying(255) NOT NULL,
    is_active boolean NOT NULL
);

--
-- Name: report_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.report_versions (
    id uuid NOT NULL,
    tipo character varying(40) NOT NULL,
    report_id uuid NOT NULL,
    versao integer NOT NULL,
    evento character varying(30) NOT NULL,
    status_anterior character varying(30),
    status_novo character varying(30),
    alteracoes jsonb,
    snapshot jsonb NOT NULL,
    motivo text,
    alterado_por uuid,
    alterado_em timestamp with time zone NOT NULL
);

--
-- Name: slot_horario; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.slot_horario (
    id integer NOT NULL,
    turno character varying(20) NOT NULL,
    ordem integer NOT NULL,
    horario_inicio time without time zone NOT NULL,
    horario_fim time without time zone NOT NULL,
    ativo boolean NOT NULL,
    data_criacao timestamp without time zone NOT NULL,
    CONSTRAINT chk_horario CHECK ((horario_fim > horario_inicio)),
    CONSTRAINT chk_turno CHECK (((turno)::text = ANY ((ARRAY['manha'::character varying, 'tarde'::character varying, 'noite'::character varying, 'madrugada'::character varying])::text[])))
);

--
-- Name: slot_horario_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.slot_horario_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: slot_horario_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.slot_horario_id_seq OWNED BY public.slot_horario.id;

--
-- Name: turmas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.turmas (
    id uuid NOT NULL,
    unit_id uuid,
    nome character varying(255) NOT NULL,
    modalidade character varying(100) NOT NULL,
    serie_modulo character varying(100) NOT NULL,
    turno character varying(50) NOT NULL,
    nome_pasta_drive character varying(255),
    nomenclatura_padrao character varying(255),
    is_active boolean NOT NULL
);

--
-- Name: units; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.units (
    id uuid NOT NULL,
    nome character varying(255) NOT NULL
);

--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    email character varying(255) NOT NULL,
    hashed_password character varying(255),
    full_name character varying(255) NOT NULL,
    is_active boolean NOT NULL,
    role character varying(50) NOT NULL,
    email_confirmed boolean NOT NULL,
    invite_token character varying(255),
    invite_expires_at timestamp with time zone,
    invited_by uuid,
    reset_token character varying(255),
    reset_token_expires_at timestamp with time zone,
    theme_preference character varying(10) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

--
-- Name: agenda_bloqueios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_bloqueios ALTER COLUMN id SET DEFAULT nextval('public.agenda_bloqueios_id_seq'::regclass);

--
-- Name: agenda_escala_dia id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_dia ALTER COLUMN id SET DEFAULT nextval('public.agenda_escala_dia_id_seq'::regclass);

--
-- Name: agenda_escala_fixa id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_fixa ALTER COLUMN id SET DEFAULT nextval('public.agenda_escala_fixa_id_seq'::regclass);

--
-- Name: agenda_feriados id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_feriados ALTER COLUMN id SET DEFAULT nextval('public.agenda_feriados_id_seq'::regclass);

--
-- Name: agenda_intervalos id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_intervalos ALTER COLUMN id SET DEFAULT nextval('public.agenda_intervalos_id_seq'::regclass);

--
-- Name: agenda_observacoes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_observacoes ALTER COLUMN id SET DEFAULT nextval('public.agenda_observacoes_id_seq'::regclass);

--
-- Name: canal_iptv id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.canal_iptv ALTER COLUMN id SET DEFAULT nextval('public.canal_iptv_id_seq'::regclass);

--
-- Name: estudio id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.estudio ALTER COLUMN id SET DEFAULT nextval('public.estudio_id_seq'::regclass);

--
-- Name: grade_versao id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grade_versao ALTER COLUMN id SET DEFAULT nextval('public.grade_versao_id_seq'::regclass);

--
-- Name: login_attempts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_attempts ALTER COLUMN id SET DEFAULT nextval('public.login_attempts_id_seq'::regclass);

--
-- Name: slot_horario id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.slot_horario ALTER COLUMN id SET DEFAULT nextval('public.slot_horario_id_seq'::regclass);

--
-- Name: agenda_agendamentos agenda_agendamentos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_agendamentos
    ADD CONSTRAINT agenda_agendamentos_pkey PRIMARY KEY (id);

--
-- Name: agenda_bloqueios agenda_bloqueios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_bloqueios
    ADD CONSTRAINT agenda_bloqueios_pkey PRIMARY KEY (id);

--
-- Name: agenda_escala_dia agenda_escala_dia_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_dia
    ADD CONSTRAINT agenda_escala_dia_pkey PRIMARY KEY (id);

--
-- Name: agenda_escala_fixa agenda_escala_fixa_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_fixa
    ADD CONSTRAINT agenda_escala_fixa_pkey PRIMARY KEY (id);

--
-- Name: agenda_estudio_config agenda_estudio_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_estudio_config
    ADD CONSTRAINT agenda_estudio_config_pkey PRIMARY KEY (estudio_id);

--
-- Name: agenda_feriados agenda_feriados_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_feriados
    ADD CONSTRAINT agenda_feriados_pkey PRIMARY KEY (id);

--
-- Name: agenda_intervalos agenda_intervalos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_intervalos
    ADD CONSTRAINT agenda_intervalos_pkey PRIMARY KEY (id);

--
-- Name: agenda_observacoes agenda_observacoes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_observacoes
    ADD CONSTRAINT agenda_observacoes_pkey PRIMARY KEY (id);

--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);

--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);

--
-- Name: canal_iptv canal_iptv_numero_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.canal_iptv
    ADD CONSTRAINT canal_iptv_numero_key UNIQUE (numero);

--
-- Name: canal_iptv canal_iptv_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.canal_iptv
    ADD CONSTRAINT canal_iptv_pkey PRIMARY KEY (id);

--
-- Name: class_reports class_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_reports
    ADD CONSTRAINT class_reports_pkey PRIMARY KEY (id);

--
-- Name: diretores_imagem diretores_imagem_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diretores_imagem
    ADD CONSTRAINT diretores_imagem_pkey PRIMARY KEY (id);

--
-- Name: diretores_imagem diretores_imagem_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diretores_imagem
    ADD CONSTRAINT diretores_imagem_user_id_key UNIQUE (user_id);

--
-- Name: disciplinas disciplinas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.disciplinas
    ADD CONSTRAINT disciplinas_pkey PRIMARY KEY (id);

--
-- Name: estudio estudio_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.estudio
    ADD CONSTRAINT estudio_pkey PRIMARY KEY (id);

--
-- Name: grade_versao grade_versao_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grade_versao
    ADD CONSTRAINT grade_versao_pkey PRIMARY KEY (id);

--
-- Name: grades grades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grades
    ADD CONSTRAINT grades_pkey PRIMARY KEY (id);

--
-- Name: image_director_checklist_items image_director_checklist_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_checklist_items
    ADD CONSTRAINT image_director_checklist_items_pkey PRIMARY KEY (id);

--
-- Name: image_director_checklist_responses image_director_checklist_responses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_checklist_responses
    ADD CONSTRAINT image_director_checklist_responses_pkey PRIMARY KEY (id);

--
-- Name: image_director_custom_answers image_director_custom_answers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_custom_answers
    ADD CONSTRAINT image_director_custom_answers_pkey PRIMARY KEY (id);

--
-- Name: image_director_custom_questions image_director_custom_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_custom_questions
    ADD CONSTRAINT image_director_custom_questions_pkey PRIMARY KEY (id);

--
-- Name: image_director_lessons image_director_lessons_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_lessons
    ADD CONSTRAINT image_director_lessons_pkey PRIMARY KEY (id);

--
-- Name: image_director_reports image_director_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_reports
    ADD CONSTRAINT image_director_reports_pkey PRIMARY KEY (id);

--
-- Name: login_attempts login_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_attempts
    ADD CONSTRAINT login_attempts_pkey PRIMARY KEY (id);

--
-- Name: professor_disciplinas professor_disciplinas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.professor_disciplinas
    ADD CONSTRAINT professor_disciplinas_pkey PRIMARY KEY (id);

--
-- Name: professores professores_nome_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.professores
    ADD CONSTRAINT professores_nome_key UNIQUE (nome);

--
-- Name: professores professores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.professores
    ADD CONSTRAINT professores_pkey PRIMARY KEY (id);

--
-- Name: report_versions report_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_versions
    ADD CONSTRAINT report_versions_pkey PRIMARY KEY (id);

--
-- Name: slot_horario slot_horario_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.slot_horario
    ADD CONSTRAINT slot_horario_pkey PRIMARY KEY (id);

--
-- Name: turmas turmas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turmas
    ADD CONSTRAINT turmas_pkey PRIMARY KEY (id);

--
-- Name: units units_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.units
    ADD CONSTRAINT units_pkey PRIMARY KEY (id);

--
-- Name: agenda_escala_dia uq_agenda_escala_dia; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_dia
    ADD CONSTRAINT uq_agenda_escala_dia UNIQUE (data, turno, estudio_id);

--
-- Name: agenda_escala_fixa uq_agenda_escala_fixa; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_fixa
    ADD CONSTRAINT uq_agenda_escala_fixa UNIQUE (dia_semana, turno, estudio_id);

--
-- Name: report_versions uq_report_versions_tipo_report_versao; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_versions
    ADD CONSTRAINT uq_report_versions_tipo_report_versao UNIQUE (tipo, report_id, versao);

--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

--
-- Name: ix_agenda_agendamentos_data; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agenda_agendamentos_data ON public.agenda_agendamentos USING btree (data);

--
-- Name: ix_agenda_agendamentos_grade_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agenda_agendamentos_grade_id ON public.agenda_agendamentos USING btree (grade_id);

--
-- Name: ix_agenda_escala_dia_data; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agenda_escala_dia_data ON public.agenda_escala_dia USING btree (data);

--
-- Name: ix_agenda_feriados_data; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_agenda_feriados_data ON public.agenda_feriados USING btree (data);

--
-- Name: ix_agenda_intervalos_estudio_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agenda_intervalos_estudio_id ON public.agenda_intervalos USING btree (estudio_id);

--
-- Name: ix_agenda_intervalos_turno; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agenda_intervalos_turno ON public.agenda_intervalos USING btree (turno);

--
-- Name: ix_agenda_intervalos_vigente_desde; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agenda_intervalos_vigente_desde ON public.agenda_intervalos USING btree (vigente_desde);

--
-- Name: ix_agenda_observacoes_agendamento_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agenda_observacoes_agendamento_id ON public.agenda_observacoes USING btree (agendamento_id);

--
-- Name: ix_agenda_observacoes_data; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agenda_observacoes_data ON public.agenda_observacoes USING btree (data);

--
-- Name: ix_agenda_observacoes_grade_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agenda_observacoes_grade_id ON public.agenda_observacoes USING btree (grade_id);

--
-- Name: ix_audit_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_action ON public.audit_logs USING btree (action);

--
-- Name: ix_audit_logs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_created_at ON public.audit_logs USING btree (created_at);

--
-- Name: ix_audit_logs_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_id ON public.audit_logs USING btree (id);

--
-- Name: ix_class_reports_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_class_reports_id ON public.class_reports USING btree (id);

--
-- Name: ix_class_reports_nome_normalizado; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_class_reports_nome_normalizado ON public.class_reports USING btree (nome_normalizado);

--
-- Name: ix_diretores_imagem_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diretores_imagem_id ON public.diretores_imagem USING btree (id);

--
-- Name: ix_diretores_imagem_nome; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_diretores_imagem_nome ON public.diretores_imagem USING btree (nome);

--
-- Name: ix_image_director_checklist_items_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_image_director_checklist_items_id ON public.image_director_checklist_items USING btree (id);

--
-- Name: ix_image_director_checklist_responses_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_image_director_checklist_responses_id ON public.image_director_checklist_responses USING btree (id);

--
-- Name: ix_image_director_custom_answers_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_image_director_custom_answers_id ON public.image_director_custom_answers USING btree (id);

--
-- Name: ix_image_director_custom_questions_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_image_director_custom_questions_id ON public.image_director_custom_questions USING btree (id);

--
-- Name: ix_image_director_lessons_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_image_director_lessons_id ON public.image_director_lessons USING btree (id);

--
-- Name: ix_image_director_reports_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_image_director_reports_id ON public.image_director_reports USING btree (id);

--
-- Name: ix_login_attempts_email_quando; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_login_attempts_email_quando ON public.login_attempts USING btree (email, criado_em);

--
-- Name: ix_report_versions_report; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_report_versions_report ON public.report_versions USING btree (tipo, report_id);

--
-- Name: ix_turmas_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_turmas_id ON public.turmas USING btree (id);

--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);

--
-- Name: ix_users_invite_token; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_invite_token ON public.users USING btree (invite_token);

--
-- Name: ix_users_reset_token; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_reset_token ON public.users USING btree (reset_token);

--
-- Name: agenda_agendamentos agenda_agendamentos_atualizado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_agendamentos
    ADD CONSTRAINT agenda_agendamentos_atualizado_por_fkey FOREIGN KEY (atualizado_por) REFERENCES public.users(id);

--
-- Name: agenda_agendamentos agenda_agendamentos_canal_iptv_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_agendamentos
    ADD CONSTRAINT agenda_agendamentos_canal_iptv_id_fkey FOREIGN KEY (canal_iptv_id) REFERENCES public.canal_iptv(id);

--
-- Name: agenda_agendamentos agenda_agendamentos_criado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_agendamentos
    ADD CONSTRAINT agenda_agendamentos_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES public.users(id);

--
-- Name: agenda_agendamentos agenda_agendamentos_estudio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_agendamentos
    ADD CONSTRAINT agenda_agendamentos_estudio_id_fkey FOREIGN KEY (estudio_id) REFERENCES public.estudio(id);

--
-- Name: agenda_agendamentos agenda_agendamentos_grade_exibicao_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_agendamentos
    ADD CONSTRAINT agenda_agendamentos_grade_exibicao_id_fkey FOREIGN KEY (grade_exibicao_id) REFERENCES public.grades(id) ON DELETE SET NULL;

--
-- Name: agenda_agendamentos agenda_agendamentos_grade_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_agendamentos
    ADD CONSTRAINT agenda_agendamentos_grade_id_fkey FOREIGN KEY (grade_id) REFERENCES public.grades(id) ON DELETE SET NULL;

--
-- Name: agenda_agendamentos agenda_agendamentos_turma_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_agendamentos
    ADD CONSTRAINT agenda_agendamentos_turma_id_fkey FOREIGN KEY (turma_id) REFERENCES public.turmas(id);

--
-- Name: agenda_bloqueios agenda_bloqueios_atualizado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_bloqueios
    ADD CONSTRAINT agenda_bloqueios_atualizado_por_fkey FOREIGN KEY (atualizado_por) REFERENCES public.users(id);

--
-- Name: agenda_bloqueios agenda_bloqueios_estudio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_bloqueios
    ADD CONSTRAINT agenda_bloqueios_estudio_id_fkey FOREIGN KEY (estudio_id) REFERENCES public.estudio(id);

--
-- Name: agenda_escala_dia agenda_escala_dia_atualizado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_dia
    ADD CONSTRAINT agenda_escala_dia_atualizado_por_fkey FOREIGN KEY (atualizado_por) REFERENCES public.users(id);

--
-- Name: agenda_escala_dia agenda_escala_dia_diretor2_imagem_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_dia
    ADD CONSTRAINT agenda_escala_dia_diretor2_imagem_id_fkey FOREIGN KEY (diretor2_imagem_id) REFERENCES public.diretores_imagem(id);

--
-- Name: agenda_escala_dia agenda_escala_dia_diretor_imagem_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_dia
    ADD CONSTRAINT agenda_escala_dia_diretor_imagem_id_fkey FOREIGN KEY (diretor_imagem_id) REFERENCES public.diretores_imagem(id);

--
-- Name: agenda_escala_dia agenda_escala_dia_estudio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_dia
    ADD CONSTRAINT agenda_escala_dia_estudio_id_fkey FOREIGN KEY (estudio_id) REFERENCES public.estudio(id);

--
-- Name: agenda_escala_fixa agenda_escala_fixa_atualizado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_fixa
    ADD CONSTRAINT agenda_escala_fixa_atualizado_por_fkey FOREIGN KEY (atualizado_por) REFERENCES public.users(id);

--
-- Name: agenda_escala_fixa agenda_escala_fixa_diretor_imagem_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_fixa
    ADD CONSTRAINT agenda_escala_fixa_diretor_imagem_id_fkey FOREIGN KEY (diretor_imagem_id) REFERENCES public.diretores_imagem(id);

--
-- Name: agenda_escala_fixa agenda_escala_fixa_estudio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_escala_fixa
    ADD CONSTRAINT agenda_escala_fixa_estudio_id_fkey FOREIGN KEY (estudio_id) REFERENCES public.estudio(id);

--
-- Name: agenda_estudio_config agenda_estudio_config_atualizado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_estudio_config
    ADD CONSTRAINT agenda_estudio_config_atualizado_por_fkey FOREIGN KEY (atualizado_por) REFERENCES public.users(id);

--
-- Name: agenda_estudio_config agenda_estudio_config_estudio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_estudio_config
    ADD CONSTRAINT agenda_estudio_config_estudio_id_fkey FOREIGN KEY (estudio_id) REFERENCES public.estudio(id);

--
-- Name: agenda_feriados agenda_feriados_criado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_feriados
    ADD CONSTRAINT agenda_feriados_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES public.users(id);

--
-- Name: agenda_intervalos agenda_intervalos_criado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_intervalos
    ADD CONSTRAINT agenda_intervalos_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES public.users(id);

--
-- Name: agenda_intervalos agenda_intervalos_estudio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_intervalos
    ADD CONSTRAINT agenda_intervalos_estudio_id_fkey FOREIGN KEY (estudio_id) REFERENCES public.estudio(id);

--
-- Name: agenda_observacoes agenda_observacoes_agendamento_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_observacoes
    ADD CONSTRAINT agenda_observacoes_agendamento_id_fkey FOREIGN KEY (agendamento_id) REFERENCES public.agenda_agendamentos(id) ON DELETE CASCADE;

--
-- Name: agenda_observacoes agenda_observacoes_autor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_observacoes
    ADD CONSTRAINT agenda_observacoes_autor_id_fkey FOREIGN KEY (autor_id) REFERENCES public.users(id);

--
-- Name: agenda_observacoes agenda_observacoes_grade_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_observacoes
    ADD CONSTRAINT agenda_observacoes_grade_id_fkey FOREIGN KEY (grade_id) REFERENCES public.grades(id) ON DELETE SET NULL;

--
-- Name: audit_logs audit_logs_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id);

--
-- Name: audit_logs audit_logs_target_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_target_user_id_fkey FOREIGN KEY (target_user_id) REFERENCES public.users(id);

--
-- Name: class_reports class_reports_cancelado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_reports
    ADD CONSTRAINT class_reports_cancelado_por_fkey FOREIGN KEY (cancelado_por) REFERENCES public.users(id);

--
-- Name: class_reports class_reports_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_reports
    ADD CONSTRAINT class_reports_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);

--
-- Name: class_reports class_reports_diretor_imagem_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_reports
    ADD CONSTRAINT class_reports_diretor_imagem_id_fkey FOREIGN KEY (diretor_imagem_id) REFERENCES public.diretores_imagem(id);

--
-- Name: class_reports class_reports_disciplina_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_reports
    ADD CONSTRAINT class_reports_disciplina_id_fkey FOREIGN KEY (disciplina_id) REFERENCES public.disciplinas(id);

--
-- Name: class_reports class_reports_professor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_reports
    ADD CONSTRAINT class_reports_professor_id_fkey FOREIGN KEY (professor_id) REFERENCES public.professores(id);

--
-- Name: class_reports class_reports_professor_substituto_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_reports
    ADD CONSTRAINT class_reports_professor_substituto_id_fkey FOREIGN KEY (professor_substituto_id) REFERENCES public.professores(id);

--
-- Name: class_reports class_reports_turma_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_reports
    ADD CONSTRAINT class_reports_turma_id_fkey FOREIGN KEY (turma_id) REFERENCES public.turmas(id);

--
-- Name: class_reports class_reports_validado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_reports
    ADD CONSTRAINT class_reports_validado_por_fkey FOREIGN KEY (validado_por) REFERENCES public.users(id);

--
-- Name: diretores_imagem diretores_imagem_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diretores_imagem
    ADD CONSTRAINT diretores_imagem_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);

--
-- Name: grade_versao grade_versao_criado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grade_versao
    ADD CONSTRAINT grade_versao_criado_por_fkey FOREIGN KEY (criado_por) REFERENCES public.users(id);

--
-- Name: grade_versao grade_versao_turma_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grade_versao
    ADD CONSTRAINT grade_versao_turma_id_fkey FOREIGN KEY (turma_id) REFERENCES public.turmas(id);

--
-- Name: grades grades_canal_iptv_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grades
    ADD CONSTRAINT grades_canal_iptv_id_fkey FOREIGN KEY (canal_iptv_id) REFERENCES public.canal_iptv(id);

--
-- Name: grades grades_disciplina_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grades
    ADD CONSTRAINT grades_disciplina_id_fkey FOREIGN KEY (disciplina_id) REFERENCES public.disciplinas(id);

--
-- Name: grades grades_estudio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grades
    ADD CONSTRAINT grades_estudio_id_fkey FOREIGN KEY (estudio_id) REFERENCES public.estudio(id);

--
-- Name: grades grades_grade_versao_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grades
    ADD CONSTRAINT grades_grade_versao_id_fkey FOREIGN KEY (grade_versao_id) REFERENCES public.grade_versao(id);

--
-- Name: grades grades_professor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grades
    ADD CONSTRAINT grades_professor_id_fkey FOREIGN KEY (professor_id) REFERENCES public.professores(id);

--
-- Name: grades grades_slot_horario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grades
    ADD CONSTRAINT grades_slot_horario_id_fkey FOREIGN KEY (slot_horario_id) REFERENCES public.slot_horario(id);

--
-- Name: grades grades_turma_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grades
    ADD CONSTRAINT grades_turma_id_fkey FOREIGN KEY (turma_id) REFERENCES public.turmas(id);

--
-- Name: image_director_checklist_responses image_director_checklist_responses_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_checklist_responses
    ADD CONSTRAINT image_director_checklist_responses_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.image_director_checklist_items(id);

--
-- Name: image_director_checklist_responses image_director_checklist_responses_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_checklist_responses
    ADD CONSTRAINT image_director_checklist_responses_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.image_director_reports(id);

--
-- Name: image_director_custom_answers image_director_custom_answers_lesson_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_custom_answers
    ADD CONSTRAINT image_director_custom_answers_lesson_id_fkey FOREIGN KEY (lesson_id) REFERENCES public.image_director_lessons(id);

--
-- Name: image_director_custom_answers image_director_custom_answers_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_custom_answers
    ADD CONSTRAINT image_director_custom_answers_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.image_director_custom_questions(id);

--
-- Name: image_director_custom_answers image_director_custom_answers_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_custom_answers
    ADD CONSTRAINT image_director_custom_answers_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.image_director_reports(id);

--
-- Name: image_director_custom_questions image_director_custom_questions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_custom_questions
    ADD CONSTRAINT image_director_custom_questions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);

--
-- Name: image_director_lessons image_director_lessons_class_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_lessons
    ADD CONSTRAINT image_director_lessons_class_report_id_fkey FOREIGN KEY (class_report_id) REFERENCES public.class_reports(id);

--
-- Name: image_director_lessons image_director_lessons_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_lessons
    ADD CONSTRAINT image_director_lessons_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.image_director_reports(id);

--
-- Name: image_director_reports image_director_reports_cancelado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_reports
    ADD CONSTRAINT image_director_reports_cancelado_por_fkey FOREIGN KEY (cancelado_por) REFERENCES public.users(id);

--
-- Name: image_director_reports image_director_reports_class_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_reports
    ADD CONSTRAINT image_director_reports_class_report_id_fkey FOREIGN KEY (class_report_id) REFERENCES public.class_reports(id);

--
-- Name: image_director_reports image_director_reports_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_reports
    ADD CONSTRAINT image_director_reports_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);

--
-- Name: image_director_reports image_director_reports_diretor_imagem_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_reports
    ADD CONSTRAINT image_director_reports_diretor_imagem_id_fkey FOREIGN KEY (diretor_imagem_id) REFERENCES public.diretores_imagem(id);

--
-- Name: image_director_reports image_director_reports_disciplina_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_reports
    ADD CONSTRAINT image_director_reports_disciplina_id_fkey FOREIGN KEY (disciplina_id) REFERENCES public.disciplinas(id);

--
-- Name: image_director_reports image_director_reports_professor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_reports
    ADD CONSTRAINT image_director_reports_professor_id_fkey FOREIGN KEY (professor_id) REFERENCES public.professores(id);

--
-- Name: image_director_reports image_director_reports_turma_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_reports
    ADD CONSTRAINT image_director_reports_turma_id_fkey FOREIGN KEY (turma_id) REFERENCES public.turmas(id);

--
-- Name: image_director_reports image_director_reports_validado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_director_reports
    ADD CONSTRAINT image_director_reports_validado_por_fkey FOREIGN KEY (validado_por) REFERENCES public.users(id);

--
-- Name: professor_disciplinas professor_disciplinas_disciplina_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.professor_disciplinas
    ADD CONSTRAINT professor_disciplinas_disciplina_id_fkey FOREIGN KEY (disciplina_id) REFERENCES public.disciplinas(id);

--
-- Name: professor_disciplinas professor_disciplinas_professor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.professor_disciplinas
    ADD CONSTRAINT professor_disciplinas_professor_id_fkey FOREIGN KEY (professor_id) REFERENCES public.professores(id);

--
-- Name: report_versions report_versions_alterado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_versions
    ADD CONSTRAINT report_versions_alterado_por_fkey FOREIGN KEY (alterado_por) REFERENCES public.users(id);

--
-- Name: turmas turmas_unit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.turmas
    ADD CONSTRAINT turmas_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES public.units(id);

--
-- Name: users users_invited_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_invited_by_fkey FOREIGN KEY (invited_by) REFERENCES public.users(id);

--
-- PostgreSQL database dump complete
--

-- Marca a versão do Alembic (o que o "stamp head" faria)
INSERT INTO public.alembic_version (version_num) VALUES ('v4b2c3d4e5f6');

COMMIT;

SELECT count(*) AS tabelas_criadas FROM information_schema.tables WHERE table_schema = 'public';
