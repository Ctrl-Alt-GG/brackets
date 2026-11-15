-- PostgreSQL schema at revision b2e5c8d1f4a7 (commit f90cd74a).
-- Frozen upgrade baseline; independent of the current ORM metadata.

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;
CREATE TYPE public.account_type AS ENUM (
    'REGULAR'
);
CREATE TYPE public.stage_type AS ENUM (
    'SINGLE_ELIMINATION',
    'SWISS',
    'ROUND_ROBIN'
);
CREATE TYPE public.tournament_status AS ENUM (
    'OPEN',
    'ARCHIVED'
);
CREATE TYPE public.user_x_club_relation AS ENUM (
    'OWNER',
    'COLLABORATOR'
);
SET default_tablespace = '';
SET default_table_access_method = heap;
CREATE TABLE public.clubs (
    id bigint NOT NULL,
    name character varying NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE public.clubs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.clubs_id_seq OWNED BY public.clubs.id;
CREATE TABLE public.matches (
    id bigint NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    start_time timestamp with time zone,
    duration_minutes integer,
    margin_minutes integer,
    custom_duration_minutes integer,
    custom_margin_minutes integer,
    round_id bigint NOT NULL,
    stage_item_input1_id bigint,
    stage_item_input2_id bigint,
    stage_item_input1_conflict boolean NOT NULL,
    stage_item_input2_conflict boolean NOT NULL,
    stage_item_input1_winner_from_match_id bigint,
    stage_item_input2_winner_from_match_id bigint,
    stage_item_input1_score integer NOT NULL,
    stage_item_input2_score integer NOT NULL,
    scoreless_result boolean DEFAULT false NOT NULL
);
CREATE SEQUENCE public.matches_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.matches_id_seq OWNED BY public.matches.id;
CREATE TABLE public.players (
    id bigint NOT NULL,
    name character varying NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    tournament_id bigint NOT NULL,
    elo_score double precision NOT NULL,
    swiss_score double precision NOT NULL,
    wins integer NOT NULL,
    draws integer NOT NULL,
    losses integer NOT NULL,
    active boolean DEFAULT true NOT NULL
);
CREATE SEQUENCE public.players_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.players_id_seq OWNED BY public.players.id;
CREATE TABLE public.players_x_teams (
    id bigint NOT NULL,
    player_id bigint NOT NULL,
    team_id bigint NOT NULL
);
CREATE SEQUENCE public.players_x_teams_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.players_x_teams_id_seq OWNED BY public.players_x_teams.id;
CREATE TABLE public.rankings (
    id bigint NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    tournament_id bigint NOT NULL,
    "position" integer NOT NULL,
    win_points double precision NOT NULL,
    draw_points double precision NOT NULL,
    loss_points double precision NOT NULL,
    add_score_points boolean NOT NULL
);
CREATE SEQUENCE public.rankings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.rankings_id_seq OWNED BY public.rankings.id;
CREATE TABLE public.revoked_sessions (
    session_id character varying NOT NULL,
    expires timestamp with time zone NOT NULL
);
CREATE TABLE public.rounds (
    id bigint NOT NULL,
    name text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    is_draft boolean NOT NULL,
    stage_item_id bigint NOT NULL
);
CREATE SEQUENCE public.rounds_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.rounds_id_seq OWNED BY public.rounds.id;
CREATE TABLE public.stage_item_inputs (
    id bigint NOT NULL,
    slot integer NOT NULL,
    tournament_id bigint NOT NULL,
    stage_item_id bigint NOT NULL,
    team_id bigint,
    winner_from_stage_item_id bigint,
    winner_position integer,
    points double precision DEFAULT '0'::double precision NOT NULL,
    wins integer DEFAULT 0 NOT NULL,
    draws integer DEFAULT 0 NOT NULL,
    losses integer DEFAULT 0 NOT NULL
);
CREATE SEQUENCE public.stage_item_inputs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.stage_item_inputs_id_seq OWNED BY public.stage_item_inputs.id;
CREATE TABLE public.stage_items (
    id bigint NOT NULL,
    name text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    stage_id bigint NOT NULL,
    team_count integer NOT NULL,
    ranking_id bigint NOT NULL,
    type public.stage_type NOT NULL
);
CREATE SEQUENCE public.stage_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.stage_items_id_seq OWNED BY public.stage_items.id;
CREATE TABLE public.stages (
    id bigint NOT NULL,
    name character varying NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    tournament_id bigint NOT NULL,
    is_active boolean DEFAULT false NOT NULL,
    custom_duration_minutes integer
);
CREATE SEQUENCE public.stages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.stages_id_seq OWNED BY public.stages.id;
CREATE TABLE public.teams (
    id bigint NOT NULL,
    name character varying NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    tournament_id bigint NOT NULL,
    active boolean DEFAULT true NOT NULL,
    elo_score double precision DEFAULT '0'::double precision NOT NULL,
    swiss_score double precision DEFAULT '0'::double precision NOT NULL,
    wins integer DEFAULT 0 NOT NULL,
    draws integer DEFAULT 0 NOT NULL,
    losses integer DEFAULT 0 NOT NULL,
    logo_path character varying
);
CREATE SEQUENCE public.teams_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.teams_id_seq OWNED BY public.teams.id;
CREATE TABLE public.tournaments (
    id bigint NOT NULL,
    name character varying NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    start_time timestamp with time zone NOT NULL,
    club_id bigint NOT NULL,
    dashboard_public boolean NOT NULL,
    logo_path character varying,
    dashboard_endpoint character varying,
    players_can_be_in_multiple_teams boolean DEFAULT false NOT NULL,
    duration_minutes integer DEFAULT 15 NOT NULL,
    margin_minutes integer DEFAULT 5 NOT NULL,
    status public.tournament_status DEFAULT 'OPEN'::public.tournament_status NOT NULL
);
CREATE SEQUENCE public.tournaments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.tournaments_id_seq OWNED BY public.tournaments.id;
CREATE TABLE public.users (
    id bigint NOT NULL,
    email character varying NOT NULL,
    name character varying NOT NULL,
    password_hash character varying NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    account_type public.account_type NOT NULL
);
CREATE SEQUENCE public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;
CREATE TABLE public.users_x_clubs (
    id bigint NOT NULL,
    club_id bigint NOT NULL,
    user_id bigint NOT NULL,
    relation public.user_x_club_relation NOT NULL
);
CREATE SEQUENCE public.users_x_clubs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.users_x_clubs_id_seq OWNED BY public.users_x_clubs.id;
ALTER TABLE ONLY public.clubs ALTER COLUMN id SET DEFAULT nextval('public.clubs_id_seq'::regclass);
ALTER TABLE ONLY public.matches ALTER COLUMN id SET DEFAULT nextval('public.matches_id_seq'::regclass);
ALTER TABLE ONLY public.players ALTER COLUMN id SET DEFAULT nextval('public.players_id_seq'::regclass);
ALTER TABLE ONLY public.players_x_teams ALTER COLUMN id SET DEFAULT nextval('public.players_x_teams_id_seq'::regclass);
ALTER TABLE ONLY public.rankings ALTER COLUMN id SET DEFAULT nextval('public.rankings_id_seq'::regclass);
ALTER TABLE ONLY public.rounds ALTER COLUMN id SET DEFAULT nextval('public.rounds_id_seq'::regclass);
ALTER TABLE ONLY public.stage_item_inputs ALTER COLUMN id SET DEFAULT nextval('public.stage_item_inputs_id_seq'::regclass);
ALTER TABLE ONLY public.stage_items ALTER COLUMN id SET DEFAULT nextval('public.stage_items_id_seq'::regclass);
ALTER TABLE ONLY public.stages ALTER COLUMN id SET DEFAULT nextval('public.stages_id_seq'::regclass);
ALTER TABLE ONLY public.teams ALTER COLUMN id SET DEFAULT nextval('public.teams_id_seq'::regclass);
ALTER TABLE ONLY public.tournaments ALTER COLUMN id SET DEFAULT nextval('public.tournaments_id_seq'::regclass);
ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);
ALTER TABLE ONLY public.users_x_clubs ALTER COLUMN id SET DEFAULT nextval('public.users_x_clubs_id_seq'::regclass);
ALTER TABLE ONLY public.clubs
    ADD CONSTRAINT clubs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.matches
    ADD CONSTRAINT matches_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.players
    ADD CONSTRAINT players_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.players_x_teams
    ADD CONSTRAINT players_x_teams_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.rankings
    ADD CONSTRAINT rankings_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.revoked_sessions
    ADD CONSTRAINT revoked_sessions_pkey PRIMARY KEY (session_id);
ALTER TABLE ONLY public.rounds
    ADD CONSTRAINT rounds_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.stage_item_inputs
    ADD CONSTRAINT stage_item_inputs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.stage_item_inputs
    ADD CONSTRAINT stage_item_inputs_stage_item_id_team_id_key UNIQUE (stage_item_id, team_id);
ALTER TABLE ONLY public.stage_item_inputs
    ADD CONSTRAINT stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key UNIQUE (stage_item_id, winner_from_stage_item_id, winner_position);
ALTER TABLE ONLY public.stage_items
    ADD CONSTRAINT stage_items_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.stages
    ADD CONSTRAINT stages_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.tournaments
    ADD CONSTRAINT tournaments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.users_x_clubs
    ADD CONSTRAINT users_x_clubs_club_id_user_id_key UNIQUE (club_id, user_id);
ALTER TABLE ONLY public.users_x_clubs
    ADD CONSTRAINT users_x_clubs_pkey PRIMARY KEY (id);
CREATE INDEX ix_clubs_id ON public.clubs USING btree (id);
CREATE INDEX ix_clubs_name ON public.clubs USING btree (name);
CREATE INDEX ix_matches_id ON public.matches USING btree (id);
CREATE INDEX ix_players_active ON public.players USING btree (active);
CREATE INDEX ix_players_id ON public.players USING btree (id);
CREATE INDEX ix_players_name ON public.players USING btree (name);
CREATE INDEX ix_players_tournament_id ON public.players USING btree (tournament_id);
CREATE INDEX ix_players_x_teams_id ON public.players_x_teams USING btree (id);
CREATE INDEX ix_rankings_id ON public.rankings USING btree (id);
CREATE INDEX ix_rankings_tournament_id ON public.rankings USING btree (tournament_id);
CREATE INDEX ix_revoked_sessions_expires ON public.revoked_sessions USING btree (expires);
CREATE INDEX ix_rounds_id ON public.rounds USING btree (id);
CREATE INDEX ix_stage_item_inputs_id ON public.stage_item_inputs USING btree (id);
CREATE INDEX ix_stage_item_inputs_stage_item_id ON public.stage_item_inputs USING btree (stage_item_id);
CREATE INDEX ix_stage_item_inputs_tournament_id ON public.stage_item_inputs USING btree (tournament_id);
CREATE INDEX ix_stage_items_id ON public.stage_items USING btree (id);
CREATE INDEX ix_stage_items_stage_id ON public.stage_items USING btree (stage_id);
CREATE INDEX ix_stages_id ON public.stages USING btree (id);
CREATE INDEX ix_stages_name ON public.stages USING btree (name);
CREATE INDEX ix_stages_tournament_id ON public.stages USING btree (tournament_id);
CREATE INDEX ix_teams_active ON public.teams USING btree (active);
CREATE INDEX ix_teams_id ON public.teams USING btree (id);
CREATE INDEX ix_teams_name ON public.teams USING btree (name);
CREATE INDEX ix_teams_tournament_id ON public.teams USING btree (tournament_id);
CREATE INDEX ix_tournaments_club_id ON public.tournaments USING btree (club_id);
CREATE UNIQUE INDEX ix_tournaments_dashboard_endpoint_lower ON public.tournaments USING btree (lower((dashboard_endpoint)::text));
CREATE INDEX ix_tournaments_id ON public.tournaments USING btree (id);
CREATE INDEX ix_tournaments_name ON public.tournaments USING btree (name);
CREATE INDEX ix_tournaments_status ON public.tournaments USING btree (status);
CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);
CREATE UNIQUE INDEX ix_users_email_lower ON public.users USING btree (lower((email)::text));
CREATE INDEX ix_users_id ON public.users USING btree (id);
CREATE INDEX ix_users_x_clubs_id ON public.users_x_clubs USING btree (id);
ALTER TABLE ONLY public.matches
    ADD CONSTRAINT matches_round_id_fkey FOREIGN KEY (round_id) REFERENCES public.rounds(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.matches
    ADD CONSTRAINT matches_stage_item_input1_id_fkey FOREIGN KEY (stage_item_input1_id) REFERENCES public.stage_item_inputs(id);
ALTER TABLE ONLY public.matches
    ADD CONSTRAINT matches_stage_item_input1_winner_from_match_id_fkey FOREIGN KEY (stage_item_input1_winner_from_match_id) REFERENCES public.matches(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.matches
    ADD CONSTRAINT matches_stage_item_input2_id_fkey FOREIGN KEY (stage_item_input2_id) REFERENCES public.stage_item_inputs(id);
ALTER TABLE ONLY public.matches
    ADD CONSTRAINT matches_stage_item_input2_winner_from_match_id_fkey FOREIGN KEY (stage_item_input2_winner_from_match_id) REFERENCES public.matches(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.players
    ADD CONSTRAINT players_tournament_id_fkey FOREIGN KEY (tournament_id) REFERENCES public.tournaments(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.players_x_teams
    ADD CONSTRAINT players_x_teams_player_id_fkey FOREIGN KEY (player_id) REFERENCES public.players(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.players_x_teams
    ADD CONSTRAINT players_x_teams_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.rankings
    ADD CONSTRAINT rankings_tournament_id_fkey FOREIGN KEY (tournament_id) REFERENCES public.tournaments(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.rounds
    ADD CONSTRAINT rounds_stage_item_id_fkey FOREIGN KEY (stage_item_id) REFERENCES public.stage_items(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.stage_item_inputs
    ADD CONSTRAINT stage_item_inputs_stage_item_id_fkey FOREIGN KEY (stage_item_id) REFERENCES public.stage_items(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.stage_item_inputs
    ADD CONSTRAINT stage_item_inputs_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id);
ALTER TABLE ONLY public.stage_item_inputs
    ADD CONSTRAINT stage_item_inputs_tournament_id_fkey FOREIGN KEY (tournament_id) REFERENCES public.tournaments(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.stage_item_inputs
    ADD CONSTRAINT stage_item_inputs_winner_from_stage_item_id_fkey FOREIGN KEY (winner_from_stage_item_id) REFERENCES public.stage_items(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.stage_items
    ADD CONSTRAINT stage_items_ranking_id_fkey FOREIGN KEY (ranking_id) REFERENCES public.rankings(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.stage_items
    ADD CONSTRAINT stage_items_stage_id_fkey FOREIGN KEY (stage_id) REFERENCES public.stages(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.stages
    ADD CONSTRAINT stages_tournament_id_fkey FOREIGN KEY (tournament_id) REFERENCES public.tournaments(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_tournament_id_fkey FOREIGN KEY (tournament_id) REFERENCES public.tournaments(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.tournaments
    ADD CONSTRAINT tournaments_club_id_fkey FOREIGN KEY (club_id) REFERENCES public.clubs(id);
ALTER TABLE ONLY public.users_x_clubs
    ADD CONSTRAINT users_x_clubs_club_id_fkey FOREIGN KEY (club_id) REFERENCES public.clubs(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.users_x_clubs
    ADD CONSTRAINT users_x_clubs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
