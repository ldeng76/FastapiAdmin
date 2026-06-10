--
-- PostgreSQL database dump
--

\restrict U84VGCVMrsljQl8C3zlCI31HzTnzJhIQqXq4FvOU82CzFlE476WyEoS3uEhMqE8

-- Dumped from database version 17.5 (ServBay)
-- Dumped by pg_dump version 18.2

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

--
-- Name: ai; Type: SCHEMA; Schema: -; Owner: root
--

CREATE SCHEMA ai;


ALTER SCHEMA ai OWNER TO root;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agno_schema_versions; Type: TABLE; Schema: ai; Owner: root
--

CREATE TABLE ai.agno_schema_versions (
    table_name character varying NOT NULL,
    version character varying NOT NULL,
    created_at character varying NOT NULL,
    updated_at character varying
);


ALTER TABLE ai.agno_schema_versions OWNER TO root;

--
-- Name: agno_sessions; Type: TABLE; Schema: ai; Owner: root
--

CREATE TABLE ai.agno_sessions (
    session_id character varying NOT NULL,
    session_type character varying NOT NULL,
    agent_id character varying,
    team_id character varying,
    workflow_id character varying,
    user_id character varying,
    session_data jsonb,
    agent_data jsonb,
    team_data jsonb,
    workflow_data jsonb,
    metadata jsonb,
    runs jsonb,
    summary jsonb,
    created_at bigint NOT NULL,
    updated_at bigint
);


ALTER TABLE ai.agno_sessions OWNER TO root;

--
-- Name: app_portal; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.app_portal (
    name character varying(64) NOT NULL,
    access_url character varying(500) NOT NULL,
    icon_url character varying(300),
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone,
    tenant_id integer NOT NULL,
    created_id integer,
    updated_id integer,
    deleted_id integer
);


ALTER TABLE public.app_portal OWNER TO root;

--
-- Name: TABLE app_portal; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.app_portal IS '门户应用';


--
-- Name: COLUMN app_portal.name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.name IS '应用名称';


--
-- Name: COLUMN app_portal.access_url; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.access_url IS '访问地址';


--
-- Name: COLUMN app_portal.icon_url; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.icon_url IS '应用图标URL';


--
-- Name: COLUMN app_portal.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.id IS '主键ID';


--
-- Name: COLUMN app_portal.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN app_portal.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN app_portal.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.description IS '备注/描述';


--
-- Name: COLUMN app_portal.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.created_time IS '创建时间';


--
-- Name: COLUMN app_portal.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.updated_time IS '更新时间';


--
-- Name: COLUMN app_portal.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN app_portal.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.deleted_time IS '删除时间';


--
-- Name: COLUMN app_portal.tenant_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.tenant_id IS '租户ID';


--
-- Name: COLUMN app_portal.created_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.created_id IS '创建人ID';


--
-- Name: COLUMN app_portal.updated_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.updated_id IS '更新人ID';


--
-- Name: COLUMN app_portal.deleted_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.app_portal.deleted_id IS '删除人ID';


--
-- Name: app_portal_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.app_portal_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.app_portal_id_seq OWNER TO root;

--
-- Name: app_portal_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.app_portal_id_seq OWNED BY public.app_portal.id;


--
-- Name: apscheduler_jobs; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.apscheduler_jobs (
    id character varying(191) NOT NULL,
    next_run_time double precision,
    job_state bytea NOT NULL
);


ALTER TABLE public.apscheduler_jobs OWNER TO root;

--
-- Name: gen_demo; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.gen_demo (
    name character varying(64) NOT NULL,
    a integer,
    b bigint,
    c double precision,
    d boolean NOT NULL,
    e date,
    f time without time zone,
    g timestamp without time zone,
    h text,
    i json,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone,
    created_id integer,
    updated_id integer,
    deleted_id integer
);


ALTER TABLE public.gen_demo OWNER TO root;

--
-- Name: TABLE gen_demo; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.gen_demo IS '示例表';


--
-- Name: COLUMN gen_demo.name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.name IS '名称';


--
-- Name: COLUMN gen_demo.a; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.a IS '整数';


--
-- Name: COLUMN gen_demo.b; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.b IS '大整数';


--
-- Name: COLUMN gen_demo.c; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.c IS '浮点数';


--
-- Name: COLUMN gen_demo.d; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.d IS '布尔型';


--
-- Name: COLUMN gen_demo.e; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.e IS '日期';


--
-- Name: COLUMN gen_demo.f; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.f IS '时间';


--
-- Name: COLUMN gen_demo.g; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.g IS '日期时间';


--
-- Name: COLUMN gen_demo.h; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.h IS '长文本';


--
-- Name: COLUMN gen_demo.i; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.i IS '元数据(JSON格式)';


--
-- Name: COLUMN gen_demo.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.id IS '主键ID';


--
-- Name: COLUMN gen_demo.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN gen_demo.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN gen_demo.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.description IS '备注/描述';


--
-- Name: COLUMN gen_demo.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.created_time IS '创建时间';


--
-- Name: COLUMN gen_demo.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.updated_time IS '更新时间';


--
-- Name: COLUMN gen_demo.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN gen_demo.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.deleted_time IS '删除时间';


--
-- Name: COLUMN gen_demo.created_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.created_id IS '创建人ID';


--
-- Name: COLUMN gen_demo.updated_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.updated_id IS '更新人ID';


--
-- Name: COLUMN gen_demo.deleted_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo.deleted_id IS '删除人ID';


--
-- Name: gen_demo01; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.gen_demo01 (
    name character varying(64) NOT NULL,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone,
    created_id integer,
    updated_id integer,
    deleted_id integer
);


ALTER TABLE public.gen_demo01 OWNER TO root;

--
-- Name: TABLE gen_demo01; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.gen_demo01 IS '示例1表';


--
-- Name: COLUMN gen_demo01.name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo01.name IS '名称';


--
-- Name: COLUMN gen_demo01.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo01.id IS '主键ID';


--
-- Name: COLUMN gen_demo01.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo01.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN gen_demo01.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo01.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN gen_demo01.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo01.description IS '备注/描述';


--
-- Name: COLUMN gen_demo01.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo01.created_time IS '创建时间';


--
-- Name: COLUMN gen_demo01.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo01.updated_time IS '更新时间';


--
-- Name: COLUMN gen_demo01.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo01.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN gen_demo01.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo01.deleted_time IS '删除时间';


--
-- Name: COLUMN gen_demo01.created_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo01.created_id IS '创建人ID';


--
-- Name: COLUMN gen_demo01.updated_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo01.updated_id IS '更新人ID';


--
-- Name: COLUMN gen_demo01.deleted_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_demo01.deleted_id IS '删除人ID';


--
-- Name: gen_demo01_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.gen_demo01_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gen_demo01_id_seq OWNER TO root;

--
-- Name: gen_demo01_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.gen_demo01_id_seq OWNED BY public.gen_demo01.id;


--
-- Name: gen_demo_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.gen_demo_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gen_demo_id_seq OWNER TO root;

--
-- Name: gen_demo_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.gen_demo_id_seq OWNED BY public.gen_demo.id;


--
-- Name: gen_table; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.gen_table (
    table_name character varying(200) NOT NULL,
    table_comment character varying(500),
    class_name character varying(100) NOT NULL,
    package_name character varying(100),
    module_name character varying(30),
    business_name character varying(30),
    function_name character varying(100),
    sub_table_name character varying(64) DEFAULT NULL::character varying,
    sub_table_fk_name character varying(64) DEFAULT NULL::character varying,
    parent_menu_id integer,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone,
    created_id integer,
    updated_id integer,
    deleted_id integer
);


ALTER TABLE public.gen_table OWNER TO root;

--
-- Name: TABLE gen_table; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.gen_table IS '代码生成表';


--
-- Name: COLUMN gen_table.table_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.table_name IS '表名称';


--
-- Name: COLUMN gen_table.table_comment; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.table_comment IS '表描述';


--
-- Name: COLUMN gen_table.class_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.class_name IS '实体类名称';


--
-- Name: COLUMN gen_table.package_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.package_name IS '生成包路径';


--
-- Name: COLUMN gen_table.module_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.module_name IS '生成模块名';


--
-- Name: COLUMN gen_table.business_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.business_name IS '生成业务名';


--
-- Name: COLUMN gen_table.function_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.function_name IS '生成功能名';


--
-- Name: COLUMN gen_table.sub_table_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.sub_table_name IS '关联子表的表名';


--
-- Name: COLUMN gen_table.sub_table_fk_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.sub_table_fk_name IS '子表关联的外键名';


--
-- Name: COLUMN gen_table.parent_menu_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.parent_menu_id IS '父菜单ID';


--
-- Name: COLUMN gen_table.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.id IS '主键ID';


--
-- Name: COLUMN gen_table.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN gen_table.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN gen_table.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.description IS '备注/描述';


--
-- Name: COLUMN gen_table.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.created_time IS '创建时间';


--
-- Name: COLUMN gen_table.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.updated_time IS '更新时间';


--
-- Name: COLUMN gen_table.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN gen_table.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.deleted_time IS '删除时间';


--
-- Name: COLUMN gen_table.created_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.created_id IS '创建人ID';


--
-- Name: COLUMN gen_table.updated_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.updated_id IS '更新人ID';


--
-- Name: COLUMN gen_table.deleted_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table.deleted_id IS '删除人ID';


--
-- Name: gen_table_column; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.gen_table_column (
    column_name character varying(200) NOT NULL,
    column_comment character varying(500),
    column_type character varying(100) NOT NULL,
    column_length character varying(50),
    column_default character varying(200),
    is_pk boolean DEFAULT false NOT NULL,
    is_increment boolean DEFAULT false NOT NULL,
    is_nullable boolean DEFAULT true NOT NULL,
    is_unique boolean DEFAULT false NOT NULL,
    python_type character varying(100),
    python_field character varying(200),
    is_insert boolean DEFAULT true NOT NULL,
    is_edit boolean DEFAULT true NOT NULL,
    is_list boolean DEFAULT true NOT NULL,
    is_query boolean DEFAULT false NOT NULL,
    query_type character varying(50),
    html_type character varying(100),
    dict_type character varying(200),
    sort integer NOT NULL,
    table_id integer NOT NULL,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone,
    created_id integer,
    updated_id integer,
    deleted_id integer
);


ALTER TABLE public.gen_table_column OWNER TO root;

--
-- Name: TABLE gen_table_column; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.gen_table_column IS '代码生成表字段';


--
-- Name: COLUMN gen_table_column.column_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.column_name IS '列名称';


--
-- Name: COLUMN gen_table_column.column_comment; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.column_comment IS '列描述';


--
-- Name: COLUMN gen_table_column.column_type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.column_type IS '列类型';


--
-- Name: COLUMN gen_table_column.column_length; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.column_length IS '列长度';


--
-- Name: COLUMN gen_table_column.column_default; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.column_default IS '列默认值';


--
-- Name: COLUMN gen_table_column.is_pk; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.is_pk IS '是否主键';


--
-- Name: COLUMN gen_table_column.is_increment; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.is_increment IS '是否自增';


--
-- Name: COLUMN gen_table_column.is_nullable; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.is_nullable IS '是否允许为空';


--
-- Name: COLUMN gen_table_column.is_unique; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.is_unique IS '是否唯一';


--
-- Name: COLUMN gen_table_column.python_type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.python_type IS 'Python类型';


--
-- Name: COLUMN gen_table_column.python_field; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.python_field IS 'Python字段名';


--
-- Name: COLUMN gen_table_column.is_insert; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.is_insert IS '是否为新增字段';


--
-- Name: COLUMN gen_table_column.is_edit; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.is_edit IS '是否编辑字段';


--
-- Name: COLUMN gen_table_column.is_list; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.is_list IS '是否列表字段';


--
-- Name: COLUMN gen_table_column.is_query; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.is_query IS '是否查询字段';


--
-- Name: COLUMN gen_table_column.query_type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.query_type IS '查询方式';


--
-- Name: COLUMN gen_table_column.html_type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.html_type IS '显示类型';


--
-- Name: COLUMN gen_table_column.dict_type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.dict_type IS '字典类型';


--
-- Name: COLUMN gen_table_column.sort; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.sort IS '排序';


--
-- Name: COLUMN gen_table_column.table_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.table_id IS '归属表编号';


--
-- Name: COLUMN gen_table_column.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.id IS '主键ID';


--
-- Name: COLUMN gen_table_column.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN gen_table_column.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN gen_table_column.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.description IS '备注/描述';


--
-- Name: COLUMN gen_table_column.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.created_time IS '创建时间';


--
-- Name: COLUMN gen_table_column.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.updated_time IS '更新时间';


--
-- Name: COLUMN gen_table_column.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN gen_table_column.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.deleted_time IS '删除时间';


--
-- Name: COLUMN gen_table_column.created_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.created_id IS '创建人ID';


--
-- Name: COLUMN gen_table_column.updated_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.updated_id IS '更新人ID';


--
-- Name: COLUMN gen_table_column.deleted_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.gen_table_column.deleted_id IS '删除人ID';


--
-- Name: gen_table_column_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.gen_table_column_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gen_table_column_id_seq OWNER TO root;

--
-- Name: gen_table_column_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.gen_table_column_id_seq OWNED BY public.gen_table_column.id;


--
-- Name: gen_table_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.gen_table_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gen_table_id_seq OWNER TO root;

--
-- Name: gen_table_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.gen_table_id_seq OWNED BY public.gen_table.id;


--
-- Name: sys_dept; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_dept (
    name character varying(64) NOT NULL,
    "order" integer NOT NULL,
    code character varying(16) NOT NULL,
    leader character varying(32),
    phone character varying(11),
    email character varying(64),
    parent_id integer,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone
);


ALTER TABLE public.sys_dept OWNER TO root;

--
-- Name: TABLE sys_dept; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_dept IS '部门表';


--
-- Name: COLUMN sys_dept.name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.name IS '部门名称';


--
-- Name: COLUMN sys_dept."order"; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept."order" IS '显示排序';


--
-- Name: COLUMN sys_dept.code; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.code IS '部门编码';


--
-- Name: COLUMN sys_dept.leader; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.leader IS '部门负责人';


--
-- Name: COLUMN sys_dept.phone; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.phone IS '手机';


--
-- Name: COLUMN sys_dept.email; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.email IS '邮箱';


--
-- Name: COLUMN sys_dept.parent_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.parent_id IS '父级部门ID';


--
-- Name: COLUMN sys_dept.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.id IS '主键ID';


--
-- Name: COLUMN sys_dept.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN sys_dept.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN sys_dept.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.description IS '备注/描述';


--
-- Name: COLUMN sys_dept.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.created_time IS '创建时间';


--
-- Name: COLUMN sys_dept.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.updated_time IS '更新时间';


--
-- Name: COLUMN sys_dept.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN sys_dept.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dept.deleted_time IS '删除时间';


--
-- Name: sys_dept_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.sys_dept_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sys_dept_id_seq OWNER TO root;

--
-- Name: sys_dept_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.sys_dept_id_seq OWNED BY public.sys_dept.id;


--
-- Name: sys_dict_data; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_dict_data (
    dict_sort integer NOT NULL,
    dict_label character varying(255) NOT NULL,
    dict_value character varying(255) NOT NULL,
    css_class character varying(255),
    list_class character varying(255),
    is_default boolean NOT NULL,
    dict_type character varying(255) NOT NULL,
    dict_type_id integer NOT NULL,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone
);


ALTER TABLE public.sys_dict_data OWNER TO root;

--
-- Name: TABLE sys_dict_data; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_dict_data IS '字典数据表';


--
-- Name: COLUMN sys_dict_data.dict_sort; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.dict_sort IS '字典排序';


--
-- Name: COLUMN sys_dict_data.dict_label; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.dict_label IS '字典标签';


--
-- Name: COLUMN sys_dict_data.dict_value; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.dict_value IS '字典键值';


--
-- Name: COLUMN sys_dict_data.css_class; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.css_class IS '样式属性（其他样式扩展）';


--
-- Name: COLUMN sys_dict_data.list_class; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.list_class IS '表格回显样式';


--
-- Name: COLUMN sys_dict_data.is_default; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.is_default IS '是否默认（True是 False否）';


--
-- Name: COLUMN sys_dict_data.dict_type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.dict_type IS '字典类型';


--
-- Name: COLUMN sys_dict_data.dict_type_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.dict_type_id IS '字典类型ID';


--
-- Name: COLUMN sys_dict_data.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.id IS '主键ID';


--
-- Name: COLUMN sys_dict_data.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN sys_dict_data.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN sys_dict_data.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.description IS '备注/描述';


--
-- Name: COLUMN sys_dict_data.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.created_time IS '创建时间';


--
-- Name: COLUMN sys_dict_data.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.updated_time IS '更新时间';


--
-- Name: COLUMN sys_dict_data.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN sys_dict_data.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_data.deleted_time IS '删除时间';


--
-- Name: sys_dict_data_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.sys_dict_data_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sys_dict_data_id_seq OWNER TO root;

--
-- Name: sys_dict_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.sys_dict_data_id_seq OWNED BY public.sys_dict_data.id;


--
-- Name: sys_dict_type; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_dict_type (
    dict_name character varying(64) NOT NULL,
    dict_type character varying(255) NOT NULL,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone
);


ALTER TABLE public.sys_dict_type OWNER TO root;

--
-- Name: TABLE sys_dict_type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_dict_type IS '字典类型表';


--
-- Name: COLUMN sys_dict_type.dict_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_type.dict_name IS '字典名称';


--
-- Name: COLUMN sys_dict_type.dict_type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_type.dict_type IS '字典类型';


--
-- Name: COLUMN sys_dict_type.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_type.id IS '主键ID';


--
-- Name: COLUMN sys_dict_type.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_type.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN sys_dict_type.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_type.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN sys_dict_type.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_type.description IS '备注/描述';


--
-- Name: COLUMN sys_dict_type.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_type.created_time IS '创建时间';


--
-- Name: COLUMN sys_dict_type.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_type.updated_time IS '更新时间';


--
-- Name: COLUMN sys_dict_type.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_type.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN sys_dict_type.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_dict_type.deleted_time IS '删除时间';


--
-- Name: sys_dict_type_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.sys_dict_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sys_dict_type_id_seq OWNER TO root;

--
-- Name: sys_dict_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.sys_dict_type_id_seq OWNED BY public.sys_dict_type.id;


--
-- Name: sys_log; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_log (
    type integer NOT NULL,
    request_path character varying(255) NOT NULL,
    request_method character varying(10) NOT NULL,
    request_payload text,
    request_ip character varying(50),
    login_location character varying(255),
    request_os character varying(64),
    request_browser character varying(64),
    response_code integer NOT NULL,
    response_json text,
    process_time character varying(20),
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone,
    created_id integer,
    updated_id integer,
    deleted_id integer
);


ALTER TABLE public.sys_log OWNER TO root;

--
-- Name: TABLE sys_log; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_log IS '系统日志表';


--
-- Name: COLUMN sys_log.type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.type IS '日志类型(1登录日志 2操作日志)';


--
-- Name: COLUMN sys_log.request_path; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.request_path IS '请求路径';


--
-- Name: COLUMN sys_log.request_method; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.request_method IS '请求方式';


--
-- Name: COLUMN sys_log.request_payload; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.request_payload IS '请求体';


--
-- Name: COLUMN sys_log.request_ip; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.request_ip IS '请求IP地址';


--
-- Name: COLUMN sys_log.login_location; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.login_location IS '登录位置';


--
-- Name: COLUMN sys_log.request_os; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.request_os IS '操作系统';


--
-- Name: COLUMN sys_log.request_browser; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.request_browser IS '浏览器';


--
-- Name: COLUMN sys_log.response_code; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.response_code IS '响应状态码';


--
-- Name: COLUMN sys_log.response_json; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.response_json IS '响应体';


--
-- Name: COLUMN sys_log.process_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.process_time IS '处理时间';


--
-- Name: COLUMN sys_log.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.id IS '主键ID';


--
-- Name: COLUMN sys_log.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN sys_log.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN sys_log.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.description IS '备注/描述';


--
-- Name: COLUMN sys_log.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.created_time IS '创建时间';


--
-- Name: COLUMN sys_log.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.updated_time IS '更新时间';


--
-- Name: COLUMN sys_log.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN sys_log.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.deleted_time IS '删除时间';


--
-- Name: COLUMN sys_log.created_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.created_id IS '创建人ID';


--
-- Name: COLUMN sys_log.updated_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.updated_id IS '更新人ID';


--
-- Name: COLUMN sys_log.deleted_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_log.deleted_id IS '删除人ID';


--
-- Name: sys_log_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.sys_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sys_log_id_seq OWNER TO root;

--
-- Name: sys_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.sys_log_id_seq OWNED BY public.sys_log.id;


--
-- Name: sys_menu; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_menu (
    name character varying(50) NOT NULL,
    type integer NOT NULL,
    "order" integer NOT NULL,
    permission character varying(100),
    icon character varying(50),
    route_name character varying(100),
    route_path character varying(200),
    component_path character varying(200),
    redirect character varying(200),
    hidden boolean NOT NULL,
    keep_alive boolean NOT NULL,
    always_show boolean NOT NULL,
    title character varying(50),
    params json,
    affix boolean NOT NULL,
    parent_id integer,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone
);


ALTER TABLE public.sys_menu OWNER TO root;

--
-- Name: TABLE sys_menu; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_menu IS '菜单表';


--
-- Name: COLUMN sys_menu.name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.name IS '菜单名称';


--
-- Name: COLUMN sys_menu.type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.type IS '菜单类型(1:目录 2:菜单 3:按钮/权限 4:链接)';


--
-- Name: COLUMN sys_menu."order"; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu."order" IS '显示排序';


--
-- Name: COLUMN sys_menu.permission; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.permission IS '权限标识(如:module_system:user:query)';


--
-- Name: COLUMN sys_menu.icon; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.icon IS '菜单图标';


--
-- Name: COLUMN sys_menu.route_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.route_name IS '路由名称';


--
-- Name: COLUMN sys_menu.route_path; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.route_path IS '路由路径';


--
-- Name: COLUMN sys_menu.component_path; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.component_path IS '组件路径';


--
-- Name: COLUMN sys_menu.redirect; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.redirect IS '重定向地址';


--
-- Name: COLUMN sys_menu.hidden; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.hidden IS '是否隐藏(True:隐藏 False:显示)';


--
-- Name: COLUMN sys_menu.keep_alive; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.keep_alive IS '是否缓存(True:是 False:否)';


--
-- Name: COLUMN sys_menu.always_show; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.always_show IS '是否始终显示(True:是 False:否)';


--
-- Name: COLUMN sys_menu.title; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.title IS '菜单标题';


--
-- Name: COLUMN sys_menu.params; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.params IS '路由参数(JSON对象)';


--
-- Name: COLUMN sys_menu.affix; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.affix IS '是否固定标签页(True:是 False:否)';


--
-- Name: COLUMN sys_menu.parent_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.parent_id IS '父菜单ID';


--
-- Name: COLUMN sys_menu.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.id IS '主键ID';


--
-- Name: COLUMN sys_menu.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN sys_menu.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN sys_menu.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.description IS '备注/描述';


--
-- Name: COLUMN sys_menu.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.created_time IS '创建时间';


--
-- Name: COLUMN sys_menu.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.updated_time IS '更新时间';


--
-- Name: COLUMN sys_menu.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN sys_menu.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_menu.deleted_time IS '删除时间';


--
-- Name: sys_menu_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.sys_menu_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sys_menu_id_seq OWNER TO root;

--
-- Name: sys_menu_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.sys_menu_id_seq OWNED BY public.sys_menu.id;


--
-- Name: sys_notice; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_notice (
    notice_title character varying(64) NOT NULL,
    notice_type character varying(1) NOT NULL,
    notice_content text,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone,
    created_id integer,
    updated_id integer,
    deleted_id integer
);


ALTER TABLE public.sys_notice OWNER TO root;

--
-- Name: TABLE sys_notice; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_notice IS '通知公告表';


--
-- Name: COLUMN sys_notice.notice_title; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.notice_title IS '公告标题';


--
-- Name: COLUMN sys_notice.notice_type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.notice_type IS '公告类型(1通知 2公告)';


--
-- Name: COLUMN sys_notice.notice_content; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.notice_content IS '公告内容';


--
-- Name: COLUMN sys_notice.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.id IS '主键ID';


--
-- Name: COLUMN sys_notice.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN sys_notice.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN sys_notice.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.description IS '备注/描述';


--
-- Name: COLUMN sys_notice.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.created_time IS '创建时间';


--
-- Name: COLUMN sys_notice.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.updated_time IS '更新时间';


--
-- Name: COLUMN sys_notice.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN sys_notice.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.deleted_time IS '删除时间';


--
-- Name: COLUMN sys_notice.created_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.created_id IS '创建人ID';


--
-- Name: COLUMN sys_notice.updated_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.updated_id IS '更新人ID';


--
-- Name: COLUMN sys_notice.deleted_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_notice.deleted_id IS '删除人ID';


--
-- Name: sys_notice_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.sys_notice_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sys_notice_id_seq OWNER TO root;

--
-- Name: sys_notice_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.sys_notice_id_seq OWNED BY public.sys_notice.id;


--
-- Name: sys_param; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_param (
    config_name character varying(64) NOT NULL,
    config_key character varying(500) NOT NULL,
    config_value character varying(500),
    config_type boolean,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone
);


ALTER TABLE public.sys_param OWNER TO root;

--
-- Name: TABLE sys_param; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_param IS '系统参数表';


--
-- Name: COLUMN sys_param.config_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_param.config_name IS '参数名称';


--
-- Name: COLUMN sys_param.config_key; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_param.config_key IS '参数键名';


--
-- Name: COLUMN sys_param.config_value; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_param.config_value IS '参数键值';


--
-- Name: COLUMN sys_param.config_type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_param.config_type IS '系统内置(True:是 False:否)';


--
-- Name: COLUMN sys_param.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_param.id IS '主键ID';


--
-- Name: COLUMN sys_param.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_param.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN sys_param.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_param.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN sys_param.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_param.description IS '备注/描述';


--
-- Name: COLUMN sys_param.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_param.created_time IS '创建时间';


--
-- Name: COLUMN sys_param.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_param.updated_time IS '更新时间';


--
-- Name: COLUMN sys_param.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_param.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN sys_param.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_param.deleted_time IS '删除时间';


--
-- Name: sys_param_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.sys_param_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sys_param_id_seq OWNER TO root;

--
-- Name: sys_param_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.sys_param_id_seq OWNED BY public.sys_param.id;


--
-- Name: sys_position; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_position (
    name character varying(64) NOT NULL,
    "order" integer NOT NULL,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone,
    created_id integer,
    updated_id integer,
    deleted_id integer
);


ALTER TABLE public.sys_position OWNER TO root;

--
-- Name: TABLE sys_position; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_position IS '岗位表';


--
-- Name: COLUMN sys_position.name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position.name IS '岗位名称';


--
-- Name: COLUMN sys_position."order"; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position."order" IS '显示排序';


--
-- Name: COLUMN sys_position.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position.id IS '主键ID';


--
-- Name: COLUMN sys_position.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN sys_position.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN sys_position.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position.description IS '备注/描述';


--
-- Name: COLUMN sys_position.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position.created_time IS '创建时间';


--
-- Name: COLUMN sys_position.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position.updated_time IS '更新时间';


--
-- Name: COLUMN sys_position.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN sys_position.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position.deleted_time IS '删除时间';


--
-- Name: COLUMN sys_position.created_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position.created_id IS '创建人ID';


--
-- Name: COLUMN sys_position.updated_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position.updated_id IS '更新人ID';


--
-- Name: COLUMN sys_position.deleted_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_position.deleted_id IS '删除人ID';


--
-- Name: sys_position_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.sys_position_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sys_position_id_seq OWNER TO root;

--
-- Name: sys_position_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.sys_position_id_seq OWNED BY public.sys_position.id;


--
-- Name: sys_role; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_role (
    name character varying(64) NOT NULL,
    code character varying(16) NOT NULL,
    "order" integer NOT NULL,
    data_scope integer NOT NULL,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone
);


ALTER TABLE public.sys_role OWNER TO root;

--
-- Name: TABLE sys_role; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_role IS '角色表';


--
-- Name: COLUMN sys_role.name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role.name IS '角色名称';


--
-- Name: COLUMN sys_role.code; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role.code IS '角色编码';


--
-- Name: COLUMN sys_role."order"; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role."order" IS '显示排序';


--
-- Name: COLUMN sys_role.data_scope; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role.data_scope IS '数据权限范围(1:仅本人 2:本部门 3:本部门及以下 4:全部 5:自定义)';


--
-- Name: COLUMN sys_role.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role.id IS '主键ID';


--
-- Name: COLUMN sys_role.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN sys_role.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN sys_role.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role.description IS '备注/描述';


--
-- Name: COLUMN sys_role.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role.created_time IS '创建时间';


--
-- Name: COLUMN sys_role.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role.updated_time IS '更新时间';


--
-- Name: COLUMN sys_role.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN sys_role.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role.deleted_time IS '删除时间';


--
-- Name: sys_role_depts; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_role_depts (
    role_id integer NOT NULL,
    dept_id integer NOT NULL
);


ALTER TABLE public.sys_role_depts OWNER TO root;

--
-- Name: TABLE sys_role_depts; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_role_depts IS '角色部门关联表';


--
-- Name: COLUMN sys_role_depts.role_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role_depts.role_id IS '角色ID';


--
-- Name: COLUMN sys_role_depts.dept_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role_depts.dept_id IS '部门ID';


--
-- Name: sys_role_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.sys_role_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sys_role_id_seq OWNER TO root;

--
-- Name: sys_role_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.sys_role_id_seq OWNED BY public.sys_role.id;


--
-- Name: sys_role_menus; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_role_menus (
    role_id integer NOT NULL,
    menu_id integer NOT NULL
);


ALTER TABLE public.sys_role_menus OWNER TO root;

--
-- Name: TABLE sys_role_menus; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_role_menus IS '角色菜单关联表';


--
-- Name: COLUMN sys_role_menus.role_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role_menus.role_id IS '角色ID';


--
-- Name: COLUMN sys_role_menus.menu_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_role_menus.menu_id IS '菜单ID';


--
-- Name: sys_tenant; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_tenant (
    name character varying(100) NOT NULL,
    code character varying(100) NOT NULL,
    start_time timestamp without time zone,
    end_time timestamp without time zone,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone
);


ALTER TABLE public.sys_tenant OWNER TO root;

--
-- Name: TABLE sys_tenant; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_tenant IS '租户表';


--
-- Name: COLUMN sys_tenant.name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_tenant.name IS '租户名称';


--
-- Name: COLUMN sys_tenant.code; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_tenant.code IS '租户编码';


--
-- Name: COLUMN sys_tenant.start_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_tenant.start_time IS '开始时间';


--
-- Name: COLUMN sys_tenant.end_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_tenant.end_time IS '结束时间';


--
-- Name: COLUMN sys_tenant.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_tenant.id IS '主键ID';


--
-- Name: COLUMN sys_tenant.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_tenant.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN sys_tenant.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_tenant.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN sys_tenant.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_tenant.description IS '备注/描述';


--
-- Name: COLUMN sys_tenant.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_tenant.created_time IS '创建时间';


--
-- Name: COLUMN sys_tenant.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_tenant.updated_time IS '更新时间';


--
-- Name: COLUMN sys_tenant.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_tenant.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN sys_tenant.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_tenant.deleted_time IS '删除时间';


--
-- Name: sys_tenant_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.sys_tenant_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sys_tenant_id_seq OWNER TO root;

--
-- Name: sys_tenant_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.sys_tenant_id_seq OWNED BY public.sys_tenant.id;


--
-- Name: sys_user; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_user (
    username character varying(64) NOT NULL,
    password character varying(255) NOT NULL,
    name character varying(32) NOT NULL,
    mobile character varying(11),
    email character varying(64),
    gender character varying(1),
    avatar character varying(255),
    is_superuser boolean NOT NULL,
    last_login timestamp with time zone,
    gitee_login character varying(32),
    github_login character varying(32),
    wx_login character varying(32),
    qq_login character varying(32),
    dept_id integer,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone,
    tenant_id integer NOT NULL,
    created_id integer,
    updated_id integer,
    deleted_id integer
);


ALTER TABLE public.sys_user OWNER TO root;

--
-- Name: TABLE sys_user; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_user IS '用户表';


--
-- Name: COLUMN sys_user.username; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.username IS '用户名/登录账号';


--
-- Name: COLUMN sys_user.password; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.password IS '密码哈希';


--
-- Name: COLUMN sys_user.name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.name IS '昵称';


--
-- Name: COLUMN sys_user.mobile; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.mobile IS '手机号';


--
-- Name: COLUMN sys_user.email; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.email IS '邮箱';


--
-- Name: COLUMN sys_user.gender; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.gender IS '性别(0:男 1:女 2:未知)';


--
-- Name: COLUMN sys_user.avatar; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.avatar IS '头像URL地址';


--
-- Name: COLUMN sys_user.is_superuser; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.is_superuser IS '是否超管';


--
-- Name: COLUMN sys_user.last_login; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.last_login IS '最后登录时间';


--
-- Name: COLUMN sys_user.gitee_login; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.gitee_login IS 'Gitee登录';


--
-- Name: COLUMN sys_user.github_login; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.github_login IS 'Github登录';


--
-- Name: COLUMN sys_user.wx_login; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.wx_login IS '微信登录';


--
-- Name: COLUMN sys_user.qq_login; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.qq_login IS 'QQ登录';


--
-- Name: COLUMN sys_user.dept_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.dept_id IS '部门ID';


--
-- Name: COLUMN sys_user.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.id IS '主键ID';


--
-- Name: COLUMN sys_user.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN sys_user.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN sys_user.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.description IS '备注/描述';


--
-- Name: COLUMN sys_user.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.created_time IS '创建时间';


--
-- Name: COLUMN sys_user.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.updated_time IS '更新时间';


--
-- Name: COLUMN sys_user.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN sys_user.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.deleted_time IS '删除时间';


--
-- Name: COLUMN sys_user.tenant_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.tenant_id IS '租户ID';


--
-- Name: COLUMN sys_user.created_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.created_id IS '创建人ID';


--
-- Name: COLUMN sys_user.updated_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.updated_id IS '更新人ID';


--
-- Name: COLUMN sys_user.deleted_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user.deleted_id IS '删除人ID';


--
-- Name: sys_user_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.sys_user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sys_user_id_seq OWNER TO root;

--
-- Name: sys_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.sys_user_id_seq OWNED BY public.sys_user.id;


--
-- Name: sys_user_positions; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_user_positions (
    user_id integer NOT NULL,
    position_id integer NOT NULL
);


ALTER TABLE public.sys_user_positions OWNER TO root;

--
-- Name: TABLE sys_user_positions; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_user_positions IS '用户岗位关联表';


--
-- Name: COLUMN sys_user_positions.user_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user_positions.user_id IS '用户ID';


--
-- Name: COLUMN sys_user_positions.position_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user_positions.position_id IS '岗位ID';


--
-- Name: sys_user_roles; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.sys_user_roles (
    user_id integer NOT NULL,
    role_id integer NOT NULL
);


ALTER TABLE public.sys_user_roles OWNER TO root;

--
-- Name: TABLE sys_user_roles; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.sys_user_roles IS '用户角色关联表';


--
-- Name: COLUMN sys_user_roles.user_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user_roles.user_id IS '用户ID';


--
-- Name: COLUMN sys_user_roles.role_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.sys_user_roles.role_id IS '角色ID';


--
-- Name: task_job; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.task_job (
    job_id character varying(64) NOT NULL,
    job_name character varying(128),
    trigger_type character varying(32),
    status character varying(16) NOT NULL,
    next_run_time character varying(64),
    job_state text,
    result text,
    error text,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone
);


ALTER TABLE public.task_job OWNER TO root;

--
-- Name: TABLE task_job; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.task_job IS '任务执行日志表';


--
-- Name: COLUMN task_job.job_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.job_id IS '任务ID';


--
-- Name: COLUMN task_job.job_name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.job_name IS '任务名称';


--
-- Name: COLUMN task_job.trigger_type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.trigger_type IS '触发方式: cron/interval/date/manual';


--
-- Name: COLUMN task_job.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.status IS '执行状态';


--
-- Name: COLUMN task_job.next_run_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.next_run_time IS '下次执行时间';


--
-- Name: COLUMN task_job.job_state; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.job_state IS '任务状态信息';


--
-- Name: COLUMN task_job.result; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.result IS '执行结果';


--
-- Name: COLUMN task_job.error; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.error IS '错误信息';


--
-- Name: COLUMN task_job.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.id IS '主键ID';


--
-- Name: COLUMN task_job.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN task_job.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.description IS '备注/描述';


--
-- Name: COLUMN task_job.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.created_time IS '创建时间';


--
-- Name: COLUMN task_job.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.updated_time IS '更新时间';


--
-- Name: COLUMN task_job.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN task_job.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_job.deleted_time IS '删除时间';


--
-- Name: task_job_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.task_job_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.task_job_id_seq OWNER TO root;

--
-- Name: task_job_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.task_job_id_seq OWNED BY public.task_job.id;


--
-- Name: task_node; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.task_node (
    name character varying(64) NOT NULL,
    code character varying(32) NOT NULL,
    jobstore character varying(64),
    executor character varying(64),
    trigger character varying(64),
    trigger_args text,
    func text,
    args text,
    kwargs text,
    "coalesce" boolean,
    max_instances integer,
    start_date character varying(64),
    end_date character varying(64),
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone,
    created_id integer,
    updated_id integer,
    deleted_id integer
);


ALTER TABLE public.task_node OWNER TO root;

--
-- Name: TABLE task_node; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.task_node IS '节点类型表';


--
-- Name: COLUMN task_node.name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.name IS '节点名称';


--
-- Name: COLUMN task_node.code; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.code IS '节点编码';


--
-- Name: COLUMN task_node.jobstore; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.jobstore IS '存储器';


--
-- Name: COLUMN task_node.executor; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.executor IS '执行器';


--
-- Name: COLUMN task_node.trigger; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.trigger IS '触发器';


--
-- Name: COLUMN task_node.trigger_args; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.trigger_args IS '触发器参数';


--
-- Name: COLUMN task_node.func; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.func IS '代码块';


--
-- Name: COLUMN task_node.args; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.args IS '位置参数';


--
-- Name: COLUMN task_node.kwargs; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.kwargs IS '关键字参数';


--
-- Name: COLUMN task_node."coalesce"; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node."coalesce" IS '是否合并运行';


--
-- Name: COLUMN task_node.max_instances; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.max_instances IS '最大实例数';


--
-- Name: COLUMN task_node.start_date; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.start_date IS '开始时间';


--
-- Name: COLUMN task_node.end_date; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.end_date IS '结束时间';


--
-- Name: COLUMN task_node.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.id IS '主键ID';


--
-- Name: COLUMN task_node.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN task_node.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN task_node.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.description IS '备注/描述';


--
-- Name: COLUMN task_node.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.created_time IS '创建时间';


--
-- Name: COLUMN task_node.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.updated_time IS '更新时间';


--
-- Name: COLUMN task_node.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN task_node.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.deleted_time IS '删除时间';


--
-- Name: COLUMN task_node.created_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.created_id IS '创建人ID';


--
-- Name: COLUMN task_node.updated_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.updated_id IS '更新人ID';


--
-- Name: COLUMN task_node.deleted_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_node.deleted_id IS '删除人ID';


--
-- Name: task_node_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.task_node_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.task_node_id_seq OWNER TO root;

--
-- Name: task_node_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.task_node_id_seq OWNED BY public.task_node.id;


--
-- Name: task_workflow; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.task_workflow (
    name character varying(128) NOT NULL,
    code character varying(64) NOT NULL,
    workflow_status character varying(32) NOT NULL,
    nodes json,
    edges json,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone,
    created_id integer,
    updated_id integer,
    deleted_id integer
);


ALTER TABLE public.task_workflow OWNER TO root;

--
-- Name: TABLE task_workflow; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.task_workflow IS '工作流定义表';


--
-- Name: COLUMN task_workflow.name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.name IS '流程名称';


--
-- Name: COLUMN task_workflow.code; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.code IS '流程编码';


--
-- Name: COLUMN task_workflow.workflow_status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.workflow_status IS '流程状态: draft/published/archived';


--
-- Name: COLUMN task_workflow.nodes; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.nodes IS 'Vue Flow nodes JSON';


--
-- Name: COLUMN task_workflow.edges; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.edges IS 'Vue Flow edges JSON';


--
-- Name: COLUMN task_workflow.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.id IS '主键ID';


--
-- Name: COLUMN task_workflow.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN task_workflow.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN task_workflow.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.description IS '备注/描述';


--
-- Name: COLUMN task_workflow.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.created_time IS '创建时间';


--
-- Name: COLUMN task_workflow.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.updated_time IS '更新时间';


--
-- Name: COLUMN task_workflow.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN task_workflow.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.deleted_time IS '删除时间';


--
-- Name: COLUMN task_workflow.created_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.created_id IS '创建人ID';


--
-- Name: COLUMN task_workflow.updated_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.updated_id IS '更新人ID';


--
-- Name: COLUMN task_workflow.deleted_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow.deleted_id IS '删除人ID';


--
-- Name: task_workflow_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.task_workflow_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.task_workflow_id_seq OWNER TO root;

--
-- Name: task_workflow_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.task_workflow_id_seq OWNED BY public.task_workflow.id;


--
-- Name: task_workflow_node_type; Type: TABLE; Schema: public; Owner: root
--

CREATE TABLE public.task_workflow_node_type (
    name character varying(128) NOT NULL,
    code character varying(64) NOT NULL,
    category character varying(32) NOT NULL,
    func text NOT NULL,
    args text,
    kwargs text,
    sort_order integer NOT NULL,
    is_active boolean NOT NULL,
    id integer NOT NULL,
    uuid character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    description text,
    created_time timestamp without time zone NOT NULL,
    updated_time timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_time timestamp without time zone,
    created_id integer,
    updated_id integer,
    deleted_id integer
);


ALTER TABLE public.task_workflow_node_type OWNER TO root;

--
-- Name: TABLE task_workflow_node_type; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON TABLE public.task_workflow_node_type IS '工作流编排节点类型（非定时任务节点）';


--
-- Name: COLUMN task_workflow_node_type.name; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.name IS '显示名称';


--
-- Name: COLUMN task_workflow_node_type.code; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.code IS '节点编码，对应画布 node.type';


--
-- Name: COLUMN task_workflow_node_type.category; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.category IS '分类: trigger/action/condition/control';


--
-- Name: COLUMN task_workflow_node_type.func; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.func IS 'Python 代码块，须定义 handler(*args,**kwargs)';


--
-- Name: COLUMN task_workflow_node_type.args; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.args IS '默认位置参数，逗号分隔';


--
-- Name: COLUMN task_workflow_node_type.kwargs; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.kwargs IS '默认关键字参数 JSON';


--
-- Name: COLUMN task_workflow_node_type.sort_order; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.sort_order IS '排序';


--
-- Name: COLUMN task_workflow_node_type.is_active; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.is_active IS '是否启用';


--
-- Name: COLUMN task_workflow_node_type.id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.id IS '主键ID';


--
-- Name: COLUMN task_workflow_node_type.uuid; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.uuid IS 'UUID全局唯一标识';


--
-- Name: COLUMN task_workflow_node_type.status; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.status IS '状态(0:正常 1:禁用)';


--
-- Name: COLUMN task_workflow_node_type.description; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.description IS '备注/描述';


--
-- Name: COLUMN task_workflow_node_type.created_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.created_time IS '创建时间';


--
-- Name: COLUMN task_workflow_node_type.updated_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.updated_time IS '更新时间';


--
-- Name: COLUMN task_workflow_node_type.is_deleted; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.is_deleted IS '是否已删除(0:未删除 1:已删除)';


--
-- Name: COLUMN task_workflow_node_type.deleted_time; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.deleted_time IS '删除时间';


--
-- Name: COLUMN task_workflow_node_type.created_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.created_id IS '创建人ID';


--
-- Name: COLUMN task_workflow_node_type.updated_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.updated_id IS '更新人ID';


--
-- Name: COLUMN task_workflow_node_type.deleted_id; Type: COMMENT; Schema: public; Owner: root
--

COMMENT ON COLUMN public.task_workflow_node_type.deleted_id IS '删除人ID';


--
-- Name: task_workflow_node_type_id_seq; Type: SEQUENCE; Schema: public; Owner: root
--

CREATE SEQUENCE public.task_workflow_node_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.task_workflow_node_type_id_seq OWNER TO root;

--
-- Name: task_workflow_node_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: root
--

ALTER SEQUENCE public.task_workflow_node_type_id_seq OWNED BY public.task_workflow_node_type.id;


--
-- Name: app_portal id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.app_portal ALTER COLUMN id SET DEFAULT nextval('public.app_portal_id_seq'::regclass);


--
-- Name: gen_demo id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_demo ALTER COLUMN id SET DEFAULT nextval('public.gen_demo_id_seq'::regclass);


--
-- Name: gen_demo01 id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_demo01 ALTER COLUMN id SET DEFAULT nextval('public.gen_demo01_id_seq'::regclass);


--
-- Name: gen_table id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_table ALTER COLUMN id SET DEFAULT nextval('public.gen_table_id_seq'::regclass);


--
-- Name: gen_table_column id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_table_column ALTER COLUMN id SET DEFAULT nextval('public.gen_table_column_id_seq'::regclass);


--
-- Name: sys_dept id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_dept ALTER COLUMN id SET DEFAULT nextval('public.sys_dept_id_seq'::regclass);


--
-- Name: sys_dict_data id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_dict_data ALTER COLUMN id SET DEFAULT nextval('public.sys_dict_data_id_seq'::regclass);


--
-- Name: sys_dict_type id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_dict_type ALTER COLUMN id SET DEFAULT nextval('public.sys_dict_type_id_seq'::regclass);


--
-- Name: sys_log id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_log ALTER COLUMN id SET DEFAULT nextval('public.sys_log_id_seq'::regclass);


--
-- Name: sys_menu id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_menu ALTER COLUMN id SET DEFAULT nextval('public.sys_menu_id_seq'::regclass);


--
-- Name: sys_notice id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_notice ALTER COLUMN id SET DEFAULT nextval('public.sys_notice_id_seq'::regclass);


--
-- Name: sys_param id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_param ALTER COLUMN id SET DEFAULT nextval('public.sys_param_id_seq'::regclass);


--
-- Name: sys_position id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_position ALTER COLUMN id SET DEFAULT nextval('public.sys_position_id_seq'::regclass);


--
-- Name: sys_role id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_role ALTER COLUMN id SET DEFAULT nextval('public.sys_role_id_seq'::regclass);


--
-- Name: sys_tenant id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_tenant ALTER COLUMN id SET DEFAULT nextval('public.sys_tenant_id_seq'::regclass);


--
-- Name: sys_user id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user ALTER COLUMN id SET DEFAULT nextval('public.sys_user_id_seq'::regclass);


--
-- Name: task_job id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_job ALTER COLUMN id SET DEFAULT nextval('public.task_job_id_seq'::regclass);


--
-- Name: task_node id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_node ALTER COLUMN id SET DEFAULT nextval('public.task_node_id_seq'::regclass);


--
-- Name: task_workflow id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_workflow ALTER COLUMN id SET DEFAULT nextval('public.task_workflow_id_seq'::regclass);


--
-- Name: task_workflow_node_type id; Type: DEFAULT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_workflow_node_type ALTER COLUMN id SET DEFAULT nextval('public.task_workflow_node_type_id_seq'::regclass);


--
-- Data for Name: agno_schema_versions; Type: TABLE DATA; Schema: ai; Owner: root
--

COPY ai.agno_schema_versions (table_name, version, created_at, updated_at) FROM stdin;
agno_sessions	2.5.0	2026-03-10T22:38:46.429268	2026-03-10T22:38:46.429268
\.


--
-- Data for Name: agno_sessions; Type: TABLE DATA; Schema: ai; Owner: root
--

COPY ai.agno_sessions (session_id, session_type, agent_id, team_id, workflow_id, user_id, session_data, agent_data, team_data, workflow_data, metadata, runs, summary, created_at, updated_at) FROM stdin;
d0375348-cc9c-4103-a7ce-18d14560a785	team	\N	1	\N	admin	{"session_name": "新对话", "session_state": {}, "session_metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 898, "total_tokens": 915, "output_tokens": 17, "cache_read_tokens": 320}]}, "input_tokens": 898, "total_tokens": 915, "output_tokens": 17, "cache_read_tokens": 320}}	\N	null	\N	null	[{"input": {"input_content": "你好"}, "model": "deepseek-chat", "tools": [], "run_id": "44f0df2a-aaff-403f-bbb7-de1081d45580", "status": "COMPLETED", "content": "你好！我是你的AI助手，很高兴为你服务。有什么我可以帮助你的吗？", "metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 898, "total_tokens": 915, "output_tokens": 17, "cache_read_tokens": 320}]}, "duration": 2.4872381659988605, "input_tokens": 898, "total_tokens": 915, "output_tokens": 17, "cache_read_tokens": 320, "time_to_first_token": 2.4092763329990703}, "team_id": "1", "user_id": "admin", "messages": [{"id": "6f9ce5a8-ac26-4ca3-ada9-459641e0225c", "role": "system", "content": "You coordinate a team of specialized AI agents to fulfill the user's request. Delegate to members when their expertise or tools are needed. For straightforward requests you can handle directly — including using your own tools — respond without delegating.\\n\\n<team_members>\\n<member id=\\"admin\\" name=\\"fastapiadmin_agent\\">\\n  Role: You are a helpful AI assistant\\n  Description: 你是一个有用的AI助手，可以帮助用户回答问题和提供帮助。\\n</member>\\n</team_members>\\n\\n<how_to_respond>\\nYou operate in coordinate mode. For requests that need member expertise, select the best member(s), delegate with clear task descriptions, and synthesize their outputs into a unified response. For requests you can handle directly — simple questions, using your own tools, or general conversation — respond without delegating.\\n\\nDelegation:\\n- Match each sub-task to the member whose role and tools are the best fit. Delegate to multiple members when the request spans different areas of expertise.\\n- Write task descriptions that are self-contained: state the goal, provide relevant context from the conversation, and describe what a good result looks like.\\n- Use only the member's ID when delegating — do not prefix it with the team ID.\\n\\nAfter receiving member responses:\\n- If a response is incomplete or off-target, re-delegate with clearer instructions or try a different member.\\n- Synthesize all results into a single coherent response. Resolve contradictions, fill gaps with your own reasoning, and add structure — do not simply concatenate member outputs.\\n</how_to_respond>\\n\\n- 保持回答简洁明了\\n- 如果不确定，请说明\\n<additional_information>\\n- Use markdown to format your answers.\\n- The current time is 2026-03-12 23:50:27.983400.\\n</additional_information>\\n\\n<expected_output>\\n中文回答\\n</expected_output>", "created_at": 1773330627, "from_history": false, "stop_after_tool_call": false}, {"id": "9ee3931d-2f8f-439a-8495-28c407e1676a", "role": "user", "content": "你好", "created_at": 1773330627, "from_history": false, "stop_after_tool_call": false}, {"id": "900ca747-7b34-44f4-ae74-e6570804fcd0", "role": "assistant", "content": "你好！我是你的AI助手，很高兴为你服务。有什么我可以帮助你的吗？", "metrics": {"duration": 2.3864872499998455, "input_tokens": 898, "total_tokens": 915, "output_tokens": 17, "cache_read_tokens": 320, "time_to_first_token": 2.3864872499998455}, "created_at": 1773330627, "from_history": false, "provider_data": {"id": "ee4835e4-1a1e-4c33-b079-ec99ae7a1b55", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}, "stop_after_tool_call": false}], "created_at": 1773330627, "session_id": "d0375348-cc9c-4103-a7ce-18d14560a785", "content_type": "str", "model_provider": "OpenAI", "member_responses": [], "model_provider_data": {"id": "ee4835e4-1a1e-4c33-b079-ec99ae7a1b55", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}}]	null	1773330627	1773330630
70f63e6b-f073-4486-8b17-a98cb4a5f4fa	team	\N	1	\N	admin	{"session_name": "在吗", "session_state": {}, "session_metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 1811, "total_tokens": 1842, "output_tokens": 31, "cache_read_tokens": 640}]}, "input_tokens": 1811, "total_tokens": 1842, "output_tokens": 31, "cache_read_tokens": 640}}	\N	null	\N	null	[{"input": {"input_content": "在吗"}, "model": "deepseek-chat", "events": [], "run_id": "bffc5320-8369-471d-814b-ca66a474f358", "status": "COMPLETED", "content": "我在的！有什么可以帮助您的吗？", "metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 899, "total_tokens": 907, "output_tokens": 8, "cache_read_tokens": 320}]}, "duration": 2.5330075420006324, "input_tokens": 899, "total_tokens": 907, "output_tokens": 8, "cache_read_tokens": 320, "time_to_first_token": 1.714065957999992}, "team_id": "1", "user_id": "admin", "messages": [{"id": "7a9e0dfd-3750-4dac-913f-bb07ad2e7b20", "role": "system", "content": "You coordinate a team of specialized AI agents to fulfill the user's request. Delegate to members when their expertise or tools are needed. For straightforward requests you can handle directly — including using your own tools — respond without delegating.\\n\\n<team_members>\\n<member id=\\"admin\\" name=\\"fastapiadmin_agent\\">\\n  Role: You are a helpful AI assistant\\n  Description: 你是一个有用的AI助手，可以帮助用户回答问题和提供帮助。\\n</member>\\n</team_members>\\n\\n<how_to_respond>\\nYou operate in coordinate mode. For requests that need member expertise, select the best member(s), delegate with clear task descriptions, and synthesize their outputs into a unified response. For requests you can handle directly — simple questions, using your own tools, or general conversation — respond without delegating.\\n\\nDelegation:\\n- Match each sub-task to the member whose role and tools are the best fit. Delegate to multiple members when the request spans different areas of expertise.\\n- Write task descriptions that are self-contained: state the goal, provide relevant context from the conversation, and describe what a good result looks like.\\n- Use only the member's ID when delegating — do not prefix it with the team ID.\\n\\nAfter receiving member responses:\\n- If a response is incomplete or off-target, re-delegate with clearer instructions or try a different member.\\n- Synthesize all results into a single coherent response. Resolve contradictions, fill gaps with your own reasoning, and add structure — do not simply concatenate member outputs.\\n</how_to_respond>\\n\\n- 保持回答简洁明了\\n- 如果不确定，请说明\\n<additional_information>\\n- Use markdown to format your answers.\\n- The current time is 2026-03-12 23:26:49.742737.\\n</additional_information>\\n\\n<expected_output>\\n中文回答\\n</expected_output>", "created_at": 1773329209, "from_history": false, "stop_after_tool_call": false}, {"id": "04fdabb1-9f2c-4e9b-b133-b834a3d05ab8", "role": "user", "content": "在吗", "created_at": 1773329209, "from_history": false, "stop_after_tool_call": false}, {"id": "711208f2-81e3-4cd6-94a5-042e75f6cf08", "role": "assistant", "content": "我在的！有什么可以帮助您的吗？", "metrics": {"input_tokens": 899, "total_tokens": 907, "output_tokens": 8, "cache_read_tokens": 320, "time_to_first_token": 1.6393582500004413}, "created_at": 1773329209, "from_history": false, "provider_data": {"id": "8f1c6ef1-d4f3-413b-ba35-575a5f02bcde", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}, "stop_after_tool_call": false}], "created_at": 1773329209, "session_id": "70f63e6b-f073-4486-8b17-a98cb4a5f4fa", "content_type": "str", "model_provider": "OpenAI", "member_responses": [], "model_provider_data": {"id": "8f1c6ef1-d4f3-413b-ba35-575a5f02bcde", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}}, {"input": {"input_content": "你是谁"}, "model": "deepseek-chat", "run_id": "2636867a-f6e4-4eca-b201-68f5d0a12ffa", "status": "COMPLETED", "content": "我是您的AI助手，可以帮助您回答问题、提供信息或协助处理各种任务。有什么需要我帮忙的吗？", "metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 912, "total_tokens": 935, "output_tokens": 23, "cache_read_tokens": 320}]}, "duration": 3.5702720829995087, "input_tokens": 912, "total_tokens": 935, "output_tokens": 23, "cache_read_tokens": 320, "time_to_first_token": 1.6412430000000313}, "team_id": "1", "user_id": "admin", "messages": [{"id": "0c9fc707-6fec-4487-8475-838a7ee9e31b", "role": "system", "content": "You coordinate a team of specialized AI agents to fulfill the user's request. Delegate to members when their expertise or tools are needed. For straightforward requests you can handle directly — including using your own tools — respond without delegating.\\n\\n<team_members>\\n<member id=\\"admin\\" name=\\"fastapiadmin_agent\\">\\n  Role: You are a helpful AI assistant\\n  Description: 你是一个有用的AI助手，可以帮助用户回答问题和提供帮助。\\n</member>\\n</team_members>\\n\\n<how_to_respond>\\nYou operate in coordinate mode. For requests that need member expertise, select the best member(s), delegate with clear task descriptions, and synthesize their outputs into a unified response. For requests you can handle directly — simple questions, using your own tools, or general conversation — respond without delegating.\\n\\nDelegation:\\n- Match each sub-task to the member whose role and tools are the best fit. Delegate to multiple members when the request spans different areas of expertise.\\n- Write task descriptions that are self-contained: state the goal, provide relevant context from the conversation, and describe what a good result looks like.\\n- Use only the member's ID when delegating — do not prefix it with the team ID.\\n\\nAfter receiving member responses:\\n- If a response is incomplete or off-target, re-delegate with clearer instructions or try a different member.\\n- Synthesize all results into a single coherent response. Resolve contradictions, fill gaps with your own reasoning, and add structure — do not simply concatenate member outputs.\\n</how_to_respond>\\n\\n- 保持回答简洁明了\\n- 如果不确定，请说明\\n<additional_information>\\n- Use markdown to format your answers.\\n- The current time is 2026-03-13 00:19:14.591494.\\n</additional_information>\\n\\n<expected_output>\\n中文回答\\n</expected_output>", "created_at": 1773332354, "from_history": false, "stop_after_tool_call": false}, {"id": "f6c48ec9-213b-4e73-a056-c241b5b9a88e", "role": "user", "content": "你是谁", "created_at": 1773332354, "from_history": false, "stop_after_tool_call": false}, {"id": "c4b61a03-4789-4227-81a6-0ce10c32251b", "role": "assistant", "content": "我是您的AI助手，可以帮助您回答问题、提供信息或协助处理各种任务。有什么需要我帮忙的吗？", "metrics": {"input_tokens": 912, "total_tokens": 935, "output_tokens": 23, "cache_read_tokens": 320, "time_to_first_token": 1.5480335829997784}, "created_at": 1773332354, "from_history": false, "provider_data": {"id": "988b5a84-e099-44a0-99c8-9f5eff841b7a", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}, "stop_after_tool_call": false}], "created_at": 1773332354, "session_id": "70f63e6b-f073-4486-8b17-a98cb4a5f4fa", "content_type": "str", "model_provider": "OpenAI", "member_responses": [], "model_provider_data": {"id": "988b5a84-e099-44a0-99c8-9f5eff841b7a", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}}]	null	1773329209	1773332358
8e21f309-8b73-45b9-966a-37220a628620	team	\N	1	\N	admin	{"session_name": "你是谁", "session_state": {}, "session_metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 898, "total_tokens": 931, "output_tokens": 33, "cache_read_tokens": 320}]}, "input_tokens": 898, "total_tokens": 931, "output_tokens": 33, "cache_read_tokens": 320}}	\N	null	\N	null	[{"input": {"input_content": "你是谁"}, "model": "deepseek-chat", "run_id": "973da0dc-6842-4030-bf31-dba0bf305fb8", "status": "COMPLETED", "content": "我是您的AI助手，可以帮助您回答问题和提供帮助。我可以协调一个专门团队来处理各种任务，也可以直接回答简单的问题。\\n\\n有什么我可以为您做的吗？", "metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 898, "total_tokens": 931, "output_tokens": 33, "cache_read_tokens": 320}]}, "duration": 3.7604397920003976, "input_tokens": 898, "total_tokens": 931, "output_tokens": 33, "cache_read_tokens": 320, "time_to_first_token": 1.9425657499996305}, "team_id": "1", "user_id": "admin", "messages": [{"id": "380b9750-36aa-4af2-a44a-457f9c0ed717", "role": "system", "content": "You coordinate a team of specialized AI agents to fulfill the user's request. Delegate to members when their expertise or tools are needed. For straightforward requests you can handle directly — including using your own tools — respond without delegating.\\n\\n<team_members>\\n<member id=\\"admin\\" name=\\"fastapiadmin_agent\\">\\n  Role: You are a helpful AI assistant\\n  Description: 你是一个有用的AI助手，可以帮助用户回答问题和提供帮助。\\n</member>\\n</team_members>\\n\\n<how_to_respond>\\nYou operate in coordinate mode. For requests that need member expertise, select the best member(s), delegate with clear task descriptions, and synthesize their outputs into a unified response. For requests you can handle directly — simple questions, using your own tools, or general conversation — respond without delegating.\\n\\nDelegation:\\n- Match each sub-task to the member whose role and tools are the best fit. Delegate to multiple members when the request spans different areas of expertise.\\n- Write task descriptions that are self-contained: state the goal, provide relevant context from the conversation, and describe what a good result looks like.\\n- Use only the member's ID when delegating — do not prefix it with the team ID.\\n\\nAfter receiving member responses:\\n- If a response is incomplete or off-target, re-delegate with clearer instructions or try a different member.\\n- Synthesize all results into a single coherent response. Resolve contradictions, fill gaps with your own reasoning, and add structure — do not simply concatenate member outputs.\\n</how_to_respond>\\n\\n- 保持回答简洁明了\\n- 如果不确定，请说明\\n<additional_information>\\n- Use markdown to format your answers.\\n- The current time is 2026-03-12 23:42:23.352241.\\n</additional_information>\\n\\n<expected_output>\\n中文回答\\n</expected_output>", "created_at": 1773330143, "from_history": false, "stop_after_tool_call": false}, {"id": "b159f3aa-a036-44c2-b1d6-e6bfe44acbef", "role": "user", "content": "你是谁", "created_at": 1773330143, "from_history": false, "stop_after_tool_call": false}, {"id": "692d4bf2-aaae-4fa1-85cd-8a87fae2e7ac", "role": "assistant", "content": "我是您的AI助手，可以帮助您回答问题和提供帮助。我可以协调一个专门团队来处理各种任务，也可以直接回答简单的问题。\\n\\n有什么我可以为您做的吗？", "metrics": {"input_tokens": 898, "total_tokens": 931, "output_tokens": 33, "cache_read_tokens": 320, "time_to_first_token": 1.8599242089985637}, "created_at": 1773330143, "from_history": false, "provider_data": {"id": "f0a17d67-7f1e-48de-b34b-96a3dec94f4c", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}, "stop_after_tool_call": false}], "created_at": 1773330143, "session_id": "8e21f309-8b73-45b9-966a-37220a628620", "content_type": "str", "model_provider": "OpenAI", "member_responses": [], "model_provider_data": {"id": "f0a17d67-7f1e-48de-b34b-96a3dec94f4c", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}}]	null	1773330143	1773330147
93c0388f-8227-430a-8408-3369b89b0f99	team	\N	1	\N	admin	{"session_name": "你好他", "session_state": {}, "session_metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 899, "total_tokens": 915, "output_tokens": 16}]}, "input_tokens": 899, "total_tokens": 915, "output_tokens": 16}}	\N	null	\N	null	[{"input": {"input_content": "你好他"}, "model": "deepseek-chat", "run_id": "ea68973a-637a-42c3-b4da-7713c21f7b72", "status": "COMPLETED", "content": "你好！我是AI助手，很高兴为您服务。有什么我可以帮助您的吗？", "metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 899, "total_tokens": 915, "output_tokens": 16}]}, "duration": 2.8043415420033853, "input_tokens": 899, "total_tokens": 915, "output_tokens": 16, "time_to_first_token": 1.8211426670022774}, "team_id": "1", "user_id": "admin", "messages": [{"id": "a1b9e77c-9d9e-4973-a0cf-fab8aa0150b1", "role": "system", "content": "You coordinate a team of specialized AI agents to fulfill the user's request. Delegate to members when their expertise or tools are needed. For straightforward requests you can handle directly — including using your own tools — respond without delegating.\\n\\n<team_members>\\n<member id=\\"admin\\" name=\\"fastapiadmin_agent\\">\\n  Role: You are a helpful AI assistant\\n  Description: 你是一个有用的AI助手，可以帮助用户回答问题和提供帮助。\\n</member>\\n</team_members>\\n\\n<how_to_respond>\\nYou operate in coordinate mode. For requests that need member expertise, select the best member(s), delegate with clear task descriptions, and synthesize their outputs into a unified response. For requests you can handle directly — simple questions, using your own tools, or general conversation — respond without delegating.\\n\\nDelegation:\\n- Match each sub-task to the member whose role and tools are the best fit. Delegate to multiple members when the request spans different areas of expertise.\\n- Write task descriptions that are self-contained: state the goal, provide relevant context from the conversation, and describe what a good result looks like.\\n- Use only the member's ID when delegating — do not prefix it with the team ID.\\n\\nAfter receiving member responses:\\n- If a response is incomplete or off-target, re-delegate with clearer instructions or try a different member.\\n- Synthesize all results into a single coherent response. Resolve contradictions, fill gaps with your own reasoning, and add structure — do not simply concatenate member outputs.\\n</how_to_respond>\\n\\n- 保持回答简洁明了\\n- 如果不确定，请说明\\n<additional_information>\\n- Use markdown to format your answers.\\n- The current time is 2026-03-29 20:38:25.231562.\\n</additional_information>\\n\\n<expected_output>\\n中文回答\\n</expected_output>", "created_at": 1774787905, "from_history": false, "stop_after_tool_call": false}, {"id": "456f3a81-3084-49fc-877d-afbe04ffb9b7", "role": "user", "content": "你好他", "created_at": 1774787905, "from_history": false, "stop_after_tool_call": false}, {"id": "7747c421-a7d0-4db8-991e-f69267bdc7c5", "role": "assistant", "content": "你好！我是AI助手，很高兴为您服务。有什么我可以帮助您的吗？", "metrics": {"input_tokens": 899, "total_tokens": 915, "output_tokens": 16, "time_to_first_token": 1.7007297909985937}, "created_at": 1774787905, "from_history": false, "provider_data": {"id": "666d6f63-0b0e-49b0-8df0-6ab39d9039fc", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache_new_kvcache"}, "stop_after_tool_call": false}], "created_at": 1774787905, "session_id": "93c0388f-8227-430a-8408-3369b89b0f99", "content_type": "str", "model_provider": "OpenAI", "member_responses": [], "model_provider_data": {"id": "666d6f63-0b0e-49b0-8df0-6ab39d9039fc", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache_new_kvcache"}}]	null	1774787904	1774787907
0e2076c7-0c72-45c0-a97b-c170413720e9	team	\N	1	\N	admin	{"session_name": "你是男的女的", "session_state": {}, "session_metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 5926, "total_tokens": 6293, "output_tokens": 367, "cache_read_tokens": 1600}]}, "input_tokens": 5926, "total_tokens": 6293, "output_tokens": 367, "cache_read_tokens": 1600}}	\N	null	\N	null	[{"input": {"input_content": "你是男的女的"}, "model": "deepseek-chat", "events": [], "run_id": "99a1fea8-2950-4f2b-a2f4-63212f52c5fb", "status": "COMPLETED", "content": "我是一个AI助手，没有性别之分。我是由代码和算法构成的数字实体，旨在为您提供帮助和回答问题。\\n\\n如果您有其他问题或需要帮助，请随时告诉我！", "metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 901, "total_tokens": 936, "output_tokens": 35, "cache_read_tokens": 320}]}, "duration": 3.824642333000156, "input_tokens": 901, "total_tokens": 936, "output_tokens": 35, "cache_read_tokens": 320, "time_to_first_token": 1.7806427080013236}, "team_id": "1", "user_id": "admin", "messages": [{"id": "8539d5ee-a817-4710-822d-99686642c4df", "role": "system", "content": "You coordinate a team of specialized AI agents to fulfill the user's request. Delegate to members when their expertise or tools are needed. For straightforward requests you can handle directly — including using your own tools — respond without delegating.\\n\\n<team_members>\\n<member id=\\"admin\\" name=\\"fastapiadmin_agent\\">\\n  Role: You are a helpful AI assistant\\n  Description: 你是一个有用的AI助手，可以帮助用户回答问题和提供帮助。\\n</member>\\n</team_members>\\n\\n<how_to_respond>\\nYou operate in coordinate mode. For requests that need member expertise, select the best member(s), delegate with clear task descriptions, and synthesize their outputs into a unified response. For requests you can handle directly — simple questions, using your own tools, or general conversation — respond without delegating.\\n\\nDelegation:\\n- Match each sub-task to the member whose role and tools are the best fit. Delegate to multiple members when the request spans different areas of expertise.\\n- Write task descriptions that are self-contained: state the goal, provide relevant context from the conversation, and describe what a good result looks like.\\n- Use only the member's ID when delegating — do not prefix it with the team ID.\\n\\nAfter receiving member responses:\\n- If a response is incomplete or off-target, re-delegate with clearer instructions or try a different member.\\n- Synthesize all results into a single coherent response. Resolve contradictions, fill gaps with your own reasoning, and add structure — do not simply concatenate member outputs.\\n</how_to_respond>\\n\\n- 保持回答简洁明了\\n- 如果不确定，请说明\\n<additional_information>\\n- Use markdown to format your answers.\\n- The current time is 2026-03-13 00:09:08.236156.\\n</additional_information>\\n\\n<expected_output>\\n中文回答\\n</expected_output>", "created_at": 1773331748, "from_history": false, "stop_after_tool_call": false}, {"id": "18ed9cf5-a2a5-421e-bbb9-946f621d2a2a", "role": "user", "content": "你是男的女的", "created_at": 1773331748, "from_history": false, "stop_after_tool_call": false}, {"id": "7b3a3aa1-1fb8-4f1a-8a2c-298fef38cd7e", "role": "assistant", "content": "我是一个AI助手，没有性别之分。我是由代码和算法构成的数字实体，旨在为您提供帮助和回答问题。\\n\\n如果您有其他问题或需要帮助，请随时告诉我！", "metrics": {"input_tokens": 901, "total_tokens": 936, "output_tokens": 35, "cache_read_tokens": 320, "time_to_first_token": 1.6999175000000832}, "created_at": 1773331748, "from_history": false, "provider_data": {"id": "a1a3e8f4-dad6-45d6-9338-8c33d060f914", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}, "stop_after_tool_call": false}], "created_at": 1773331748, "session_id": "0e2076c7-0c72-45c0-a97b-c170413720e9", "content_type": "str", "model_provider": "OpenAI", "member_responses": [], "model_provider_data": {"id": "a1a3e8f4-dad6-45d6-9338-8c33d060f914", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}}, {"input": {"input_content": "好的我知道了"}, "model": "deepseek-chat", "events": [], "run_id": "9bc121c8-78e2-44b9-9ebd-758d33e845f1", "status": "COMPLETED", "content": "好的！如果您有任何其他问题或需要帮助的地方，随时可以告诉我。我很乐意为您提供帮助！", "metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 942, "total_tokens": 964, "output_tokens": 22, "cache_read_tokens": 320}]}, "duration": 2.982405832999575, "input_tokens": 942, "total_tokens": 964, "output_tokens": 22, "cache_read_tokens": 320, "time_to_first_token": 1.466743332999613}, "team_id": "1", "user_id": "admin", "messages": [{"id": "854713e7-3220-44c8-8c04-97eae9e9eb03", "role": "system", "content": "You coordinate a team of specialized AI agents to fulfill the user's request. Delegate to members when their expertise or tools are needed. For straightforward requests you can handle directly — including using your own tools — respond without delegating.\\n\\n<team_members>\\n<member id=\\"admin\\" name=\\"fastapiadmin_agent\\">\\n  Role: You are a helpful AI assistant\\n  Description: 你是一个有用的AI助手，可以帮助用户回答问题和提供帮助。\\n</member>\\n</team_members>\\n\\n<how_to_respond>\\nYou operate in coordinate mode. For requests that need member expertise, select the best member(s), delegate with clear task descriptions, and synthesize their outputs into a unified response. For requests you can handle directly — simple questions, using your own tools, or general conversation — respond without delegating.\\n\\nDelegation:\\n- Match each sub-task to the member whose role and tools are the best fit. Delegate to multiple members when the request spans different areas of expertise.\\n- Write task descriptions that are self-contained: state the goal, provide relevant context from the conversation, and describe what a good result looks like.\\n- Use only the member's ID when delegating — do not prefix it with the team ID.\\n\\nAfter receiving member responses:\\n- If a response is incomplete or off-target, re-delegate with clearer instructions or try a different member.\\n- Synthesize all results into a single coherent response. Resolve contradictions, fill gaps with your own reasoning, and add structure — do not simply concatenate member outputs.\\n</how_to_respond>\\n\\n- 保持回答简洁明了\\n- 如果不确定，请说明\\n<additional_information>\\n- Use markdown to format your answers.\\n- The current time is 2026-03-13 00:11:22.906936.\\n</additional_information>\\n\\n<expected_output>\\n中文回答\\n</expected_output>", "created_at": 1773331882, "from_history": false, "stop_after_tool_call": false}, {"id": "7f39e100-a08f-46b9-ba19-3492e7e9e6bd", "role": "user", "content": "好的我知道了", "created_at": 1773331882, "from_history": false, "stop_after_tool_call": false}, {"id": "318823e2-fb6a-48fd-9692-a5dcb407e77f", "role": "assistant", "content": "好的！如果您有任何其他问题或需要帮助的地方，随时可以告诉我。我很乐意为您提供帮助！", "metrics": {"input_tokens": 942, "total_tokens": 964, "output_tokens": 22, "cache_read_tokens": 320, "time_to_first_token": 1.3560426669992012}, "created_at": 1773331882, "from_history": false, "provider_data": {"id": "d918fcc8-da81-4463-9213-72dcf3109dd8", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}, "stop_after_tool_call": false}], "created_at": 1773331882, "session_id": "0e2076c7-0c72-45c0-a97b-c170413720e9", "content_type": "str", "model_provider": "OpenAI", "member_responses": [], "model_provider_data": {"id": "d918fcc8-da81-4463-9213-72dcf3109dd8", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}}, {"input": {"input_content": "以后我再找你"}, "model": "deepseek-chat", "events": [], "run_id": "5395a65a-f7f6-4c82-b9c3-8e4f75f11312", "status": "COMPLETED", "content": "好的，随时欢迎！我会一直在这里，当您需要帮助、有问题或者想聊天的时候，随时可以回来找我。\\n\\n祝您一切顺利！👋", "metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 971, "total_tokens": 1003, "output_tokens": 32, "cache_read_tokens": 320}]}, "duration": 3.5782694999998057, "input_tokens": 971, "total_tokens": 1003, "output_tokens": 32, "cache_read_tokens": 320, "time_to_first_token": 1.597690667000279}, "team_id": "1", "user_id": "admin", "messages": [{"id": "96f7f716-55d0-450d-946b-2a932e76cbd4", "role": "system", "content": "You coordinate a team of specialized AI agents to fulfill the user's request. Delegate to members when their expertise or tools are needed. For straightforward requests you can handle directly — including using your own tools — respond without delegating.\\n\\n<team_members>\\n<member id=\\"admin\\" name=\\"fastapiadmin_agent\\">\\n  Role: You are a helpful AI assistant\\n  Description: 你是一个有用的AI助手，可以帮助用户回答问题和提供帮助。\\n</member>\\n</team_members>\\n\\n<how_to_respond>\\nYou operate in coordinate mode. For requests that need member expertise, select the best member(s), delegate with clear task descriptions, and synthesize their outputs into a unified response. For requests you can handle directly — simple questions, using your own tools, or general conversation — respond without delegating.\\n\\nDelegation:\\n- Match each sub-task to the member whose role and tools are the best fit. Delegate to multiple members when the request spans different areas of expertise.\\n- Write task descriptions that are self-contained: state the goal, provide relevant context from the conversation, and describe what a good result looks like.\\n- Use only the member's ID when delegating — do not prefix it with the team ID.\\n\\nAfter receiving member responses:\\n- If a response is incomplete or off-target, re-delegate with clearer instructions or try a different member.\\n- Synthesize all results into a single coherent response. Resolve contradictions, fill gaps with your own reasoning, and add structure — do not simply concatenate member outputs.\\n</how_to_respond>\\n\\n- 保持回答简洁明了\\n- 如果不确定，请说明\\n<additional_information>\\n- Use markdown to format your answers.\\n- The current time is 2026-03-13 00:15:15.297981.\\n</additional_information>\\n\\n<expected_output>\\n中文回答\\n</expected_output>", "created_at": 1773332115, "from_history": false, "stop_after_tool_call": false}, {"id": "a38aa282-1009-41ca-b637-5e035d3df1cd", "role": "user", "content": "以后我再找你", "created_at": 1773332115, "from_history": false, "stop_after_tool_call": false}, {"id": "bbfae894-e2d8-4ba6-bd9e-192e8a8f7dba", "role": "assistant", "content": "好的，随时欢迎！我会一直在这里，当您需要帮助、有问题或者想聊天的时候，随时可以回来找我。\\n\\n祝您一切顺利！👋", "metrics": {"input_tokens": 971, "total_tokens": 1003, "output_tokens": 32, "cache_read_tokens": 320, "time_to_first_token": 1.5115680420003628}, "created_at": 1773332115, "from_history": false, "provider_data": {"id": "bf2c9e44-0665-45e8-847f-f1b3d06bde6c", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}, "stop_after_tool_call": false}], "created_at": 1773332115, "session_id": "0e2076c7-0c72-45c0-a97b-c170413720e9", "content_type": "str", "model_provider": "OpenAI", "member_responses": [], "model_provider_data": {"id": "bf2c9e44-0665-45e8-847f-f1b3d06bde6c", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache"}}, {"input": {"input_content": "在吗"}, "model": "deepseek-chat", "events": [], "run_id": "791d08b1-3a9d-4caa-aaf1-afd7bcf55b71", "status": "COMPLETED", "content": "在的！我一直都在这里。有什么可以帮您的吗？", "metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 1009, "total_tokens": 1022, "output_tokens": 13}]}, "duration": 2.6353677920005794, "input_tokens": 1009, "total_tokens": 1022, "output_tokens": 13, "time_to_first_token": 1.9605698750001466}, "team_id": "1", "user_id": "admin", "messages": [{"id": "6812fc0c-06f4-4e98-b083-1bc3cceef89a", "role": "system", "content": "You coordinate a team of specialized AI agents to fulfill the user's request. Delegate to members when their expertise or tools are needed. For straightforward requests you can handle directly — including using your own tools — respond without delegating.\\n\\n<team_members>\\n<member id=\\"admin\\" name=\\"fastapiadmin_agent\\">\\n  Role: You are a helpful AI assistant\\n  Description: 你是一个有用的AI助手，可以帮助用户回答问题和提供帮助。\\n</member>\\n</team_members>\\n\\n<how_to_respond>\\nYou operate in coordinate mode. For requests that need member expertise, select the best member(s), delegate with clear task descriptions, and synthesize their outputs into a unified response. For requests you can handle directly — simple questions, using your own tools, or general conversation — respond without delegating.\\n\\nDelegation:\\n- Match each sub-task to the member whose role and tools are the best fit. Delegate to multiple members when the request spans different areas of expertise.\\n- Write task descriptions that are self-contained: state the goal, provide relevant context from the conversation, and describe what a good result looks like.\\n- Use only the member's ID when delegating — do not prefix it with the team ID.\\n\\nAfter receiving member responses:\\n- If a response is incomplete or off-target, re-delegate with clearer instructions or try a different member.\\n- Synthesize all results into a single coherent response. Resolve contradictions, fill gaps with your own reasoning, and add structure — do not simply concatenate member outputs.\\n</how_to_respond>\\n\\n- 保持回答简洁明了\\n- 如果不确定，请说明\\n<additional_information>\\n- Use markdown to format your answers.\\n- The current time is 2026-03-23 23:08:13.076824.\\n</additional_information>\\n\\n<expected_output>\\n中文回答\\n</expected_output>", "created_at": 1774278493, "from_history": false, "stop_after_tool_call": false}, {"id": "5f7e5593-d788-44dd-a4f9-81dc8a78df2c", "role": "user", "content": "在吗", "created_at": 1774278493, "from_history": false, "stop_after_tool_call": false}, {"id": "af17b0d7-8cb7-4b78-aff0-96f9e218976e", "role": "assistant", "content": "在的！我一直都在这里。有什么可以帮您的吗？", "metrics": {"input_tokens": 1009, "total_tokens": 1022, "output_tokens": 13, "time_to_first_token": 1.8868432919998668}, "created_at": 1774278493, "from_history": false, "provider_data": {"id": "b75a5129-9af1-4849-9a6a-ca308eef0340", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache_new_kvcache"}, "stop_after_tool_call": false}], "created_at": 1774278493, "session_id": "0e2076c7-0c72-45c0-a97b-c170413720e9", "content_type": "str", "model_provider": "OpenAI", "member_responses": [], "model_provider_data": {"id": "b75a5129-9af1-4849-9a6a-ca308eef0340", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache_new_kvcache"}}, {"input": {"input_content": "帮我写一个python的hello worl"}, "model": "deepseek-chat", "events": [], "run_id": "9a7cc854-f560-46f2-86f4-0c707883b257", "status": "COMPLETED", "content": "我来帮您写一个Python的\\"Hello World\\"程序。这是一个非常简单的入门程序：\\n\\n```python\\n# 最简单的Hello World程序\\nprint(\\"Hello World\\")\\n\\n# 或者使用变量\\nmessage = \\"Hello World\\"\\nprint(message)\\n\\n# 或者使用函数\\ndef say_hello():\\n    print(\\"Hello World\\")\\n\\nsay_hello()\\n```\\n\\n**运行方法：**\\n1. 将代码保存为 `hello.py` 文件\\n2. 在命令行中运行：`python hello.py`\\n3. 或者直接在Python解释器中运行\\n\\n**输出结果：**\\n```\\nHello World\\n```\\n\\n这是学习Python编程的第一步！您想了解更复杂的Python程序吗？", "metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 991, "total_tokens": 1129, "output_tokens": 138, "cache_read_tokens": 320}]}, "duration": 6.201454957999886, "input_tokens": 991, "total_tokens": 1129, "output_tokens": 138, "cache_read_tokens": 320, "time_to_first_token": 1.4080830000002607}, "team_id": "1", "user_id": "admin", "messages": [{"id": "cc1002e7-82f0-45e2-b8db-160129880afe", "role": "system", "content": "You coordinate a team of specialized AI agents to fulfill the user's request. Delegate to members when their expertise or tools are needed. For straightforward requests you can handle directly — including using your own tools — respond without delegating.\\n\\n<team_members>\\n<member id=\\"admin\\" name=\\"fastapiadmin_agent\\">\\n  Role: You are a helpful AI assistant\\n  Description: 你是一个有用的AI助手，可以帮助用户回答问题和提供帮助。\\n</member>\\n</team_members>\\n\\n<how_to_respond>\\nYou operate in coordinate mode. For requests that need member expertise, select the best member(s), delegate with clear task descriptions, and synthesize their outputs into a unified response. For requests you can handle directly — simple questions, using your own tools, or general conversation — respond without delegating.\\n\\nDelegation:\\n- Match each sub-task to the member whose role and tools are the best fit. Delegate to multiple members when the request spans different areas of expertise.\\n- Write task descriptions that are self-contained: state the goal, provide relevant context from the conversation, and describe what a good result looks like.\\n- Use only the member's ID when delegating — do not prefix it with the team ID.\\n\\nAfter receiving member responses:\\n- If a response is incomplete or off-target, re-delegate with clearer instructions or try a different member.\\n- Synthesize all results into a single coherent response. Resolve contradictions, fill gaps with your own reasoning, and add structure — do not simply concatenate member outputs.\\n</how_to_respond>\\n\\n- 保持回答简洁明了\\n- 如果不确定，请说明\\n<additional_information>\\n- Use markdown to format your answers.\\n- The current time is 2026-03-23 23:08:38.810848.\\n</additional_information>\\n\\n<expected_output>\\n中文回答\\n</expected_output>", "created_at": 1774278518, "from_history": false, "stop_after_tool_call": false}, {"id": "518695f7-e8fd-4ec2-a009-4b9caade1d1d", "role": "user", "content": "帮我写一个python的hello worl", "created_at": 1774278518, "from_history": false, "stop_after_tool_call": false}, {"id": "f140147a-c0c2-44c9-8724-5809db717a55", "role": "assistant", "content": "我来帮您写一个Python的\\"Hello World\\"程序。这是一个非常简单的入门程序：\\n\\n```python\\n# 最简单的Hello World程序\\nprint(\\"Hello World\\")\\n\\n# 或者使用变量\\nmessage = \\"Hello World\\"\\nprint(message)\\n\\n# 或者使用函数\\ndef say_hello():\\n    print(\\"Hello World\\")\\n\\nsay_hello()\\n```\\n\\n**运行方法：**\\n1. 将代码保存为 `hello.py` 文件\\n2. 在命令行中运行：`python hello.py`\\n3. 或者直接在Python解释器中运行\\n\\n**输出结果：**\\n```\\nHello World\\n```\\n\\n这是学习Python编程的第一步！您想了解更复杂的Python程序吗？", "metrics": {"input_tokens": 991, "total_tokens": 1129, "output_tokens": 138, "cache_read_tokens": 320, "time_to_first_token": 1.3087896659999387}, "created_at": 1774278518, "from_history": false, "provider_data": {"id": "5b31910d-6a8e-4ba0-a2f9-dfa6f9317c30", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache_new_kvcache"}, "stop_after_tool_call": false}], "created_at": 1774278518, "session_id": "0e2076c7-0c72-45c0-a97b-c170413720e9", "content_type": "str", "model_provider": "OpenAI", "member_responses": [], "model_provider_data": {"id": "5b31910d-6a8e-4ba0-a2f9-dfa6f9317c30", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache_new_kvcache"}}, {"input": {"input_content": "请查看我提供的文件内容是什么"}, "model": "deepseek-chat", "run_id": "965fb607-566b-48c0-b4fe-87c10f3874cc", "status": "COMPLETED", "content": "我需要查看您提供的文件内容，但是目前我无法直接访问您本地的文件系统。您可以通过以下几种方式让我帮助您：\\n\\n1. **直接粘贴文件内容**：您可以将文件内容复制粘贴到聊天中\\n2. **描述文件内容**：告诉我文件的大致内容或您想了解什么\\n3. **使用代码片段**：如果是代码文件，可以用代码块格式分享\\n\\n如果您能提供文件内容，我可以帮您：\\n- 分析代码逻辑\\n- 检查语法错误\\n- 解释功能作用\\n- 提供改进建议\\n\\n请分享您想让我查看的文件内容吧！", "metrics": {"details": {"model": [{"id": "deepseek-chat", "provider": "OpenAI", "input_tokens": 1112, "total_tokens": 1239, "output_tokens": 127, "cache_read_tokens": 320}]}, "duration": 5.575905083001999, "input_tokens": 1112, "total_tokens": 1239, "output_tokens": 127, "cache_read_tokens": 320, "time_to_first_token": 1.555008583000017}, "team_id": "1", "user_id": "admin", "messages": [{"id": "87cdc130-8065-47ff-9ece-daab68c73dd7", "role": "system", "content": "You coordinate a team of specialized AI agents to fulfill the user's request. Delegate to members when their expertise or tools are needed. For straightforward requests you can handle directly — including using your own tools — respond without delegating.\\n\\n<team_members>\\n<member id=\\"admin\\" name=\\"fastapiadmin_agent\\">\\n  Role: You are a helpful AI assistant\\n  Description: 你是一个有用的AI助手，可以帮助用户回答问题和提供帮助。\\n</member>\\n</team_members>\\n\\n<how_to_respond>\\nYou operate in coordinate mode. For requests that need member expertise, select the best member(s), delegate with clear task descriptions, and synthesize their outputs into a unified response. For requests you can handle directly — simple questions, using your own tools, or general conversation — respond without delegating.\\n\\nDelegation:\\n- Match each sub-task to the member whose role and tools are the best fit. Delegate to multiple members when the request spans different areas of expertise.\\n- Write task descriptions that are self-contained: state the goal, provide relevant context from the conversation, and describe what a good result looks like.\\n- Use only the member's ID when delegating — do not prefix it with the team ID.\\n\\nAfter receiving member responses:\\n- If a response is incomplete or off-target, re-delegate with clearer instructions or try a different member.\\n- Synthesize all results into a single coherent response. Resolve contradictions, fill gaps with your own reasoning, and add structure — do not simply concatenate member outputs.\\n</how_to_respond>\\n\\n- 保持回答简洁明了\\n- 如果不确定，请说明\\n<additional_information>\\n- Use markdown to format your answers.\\n- The current time is 2026-03-29 20:40:16.570209.\\n</additional_information>\\n\\n<expected_output>\\n中文回答\\n</expected_output>", "created_at": 1774788016, "from_history": false, "stop_after_tool_call": false}, {"id": "b7423fe7-705e-49a3-bf8c-3b406d4b044b", "role": "user", "content": "请查看我提供的文件内容是什么", "created_at": 1774788016, "from_history": false, "stop_after_tool_call": false}, {"id": "96d8afe6-bdb2-482a-a954-691c4800a591", "role": "assistant", "content": "我需要查看您提供的文件内容，但是目前我无法直接访问您本地的文件系统。您可以通过以下几种方式让我帮助您：\\n\\n1. **直接粘贴文件内容**：您可以将文件内容复制粘贴到聊天中\\n2. **描述文件内容**：告诉我文件的大致内容或您想了解什么\\n3. **使用代码片段**：如果是代码文件，可以用代码块格式分享\\n\\n如果您能提供文件内容，我可以帮您：\\n- 分析代码逻辑\\n- 检查语法错误\\n- 解释功能作用\\n- 提供改进建议\\n\\n请分享您想让我查看的文件内容吧！", "metrics": {"input_tokens": 1112, "total_tokens": 1239, "output_tokens": 127, "cache_read_tokens": 320, "time_to_first_token": 1.4296587080025347}, "created_at": 1774788016, "from_history": false, "provider_data": {"id": "26dcc6a5-7ee7-44d3-8543-69328f8bb61f", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache_new_kvcache"}, "stop_after_tool_call": false}], "created_at": 1774788016, "session_id": "0e2076c7-0c72-45c0-a97b-c170413720e9", "content_type": "str", "model_provider": "OpenAI", "member_responses": [], "model_provider_data": {"id": "26dcc6a5-7ee7-44d3-8543-69328f8bb61f", "system_fingerprint": "fp_eaab8d114b_prod0820_fp8_kvcache_new_kvcache"}}]	null	1773331748	1774788022
\.


--
-- Data for Name: app_portal; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.app_portal (name, access_url, icon_url, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time, tenant_id, created_id, updated_id, deleted_id) FROM stdin;
\.


--
-- Data for Name: apscheduler_jobs; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.apscheduler_jobs (id, next_run_time, job_state) FROM stdin;
\.


--
-- Data for Name: gen_demo; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.gen_demo (name, a, b, c, d, e, f, g, h, i, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time, created_id, updated_id, deleted_id) FROM stdin;
\.


--
-- Data for Name: gen_demo01; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.gen_demo01 (name, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time, created_id, updated_id, deleted_id) FROM stdin;
\.


--
-- Data for Name: gen_table; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.gen_table (table_name, table_comment, class_name, package_name, module_name, business_name, function_name, sub_table_name, sub_table_fk_name, parent_menu_id, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time, created_id, updated_id, deleted_id) FROM stdin;
\.


--
-- Data for Name: gen_table_column; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.gen_table_column (column_name, column_comment, column_type, column_length, column_default, is_pk, is_increment, is_nullable, is_unique, python_type, python_field, is_insert, is_edit, is_list, is_query, query_type, html_type, dict_type, sort, table_id, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time, created_id, updated_id, deleted_id) FROM stdin;
\.


--
-- Data for Name: sys_dept; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_dept (name, "order", code, leader, phone, email, parent_id, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time) FROM stdin;
集团总公司	1	GROUP	部门负责人	1582112620	deptadmin@example.com	\N	1	626a4bc0-c163-4e26-91ab-bdfadfb0e5b8	0	集团总公司	2026-04-19 22:42:02.988019	2026-04-19 22:42:02.988021	f	\N
\.


--
-- Data for Name: sys_dict_data; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_dict_data (dict_sort, dict_label, dict_value, css_class, list_class, is_default, dict_type, dict_type_id, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time) FROM stdin;
1	男	0	blue	\N	t	sys_user_sex	1	1	92bd7ef1-ecd8-4f04-824d-0e74f1462f51	0	性别男	2026-04-19 22:42:02.999331	2026-04-19 22:42:02.999332	f	\N
2	女	1	pink	\N	f	sys_user_sex	1	2	69cf6a1c-2dfc-4da4-a555-1cae07af4d84	0	性别女	2026-04-19 22:42:02.999337	2026-04-19 22:42:02.999338	f	\N
3	未知	2	red	\N	f	sys_user_sex	1	3	3ab86666-f075-428e-9419-d0e84703d123	0	性别未知	2026-04-19 22:42:02.999342	2026-04-19 22:42:02.999342	f	\N
1	是	1		primary	t	sys_yes_no	2	4	3389243e-e4ed-492f-a939-8d3c79970248	0	是	2026-04-19 22:42:02.999346	2026-04-19 22:42:02.999346	f	\N
2	否	0		danger	f	sys_yes_no	2	5	00400d33-b35e-4e5a-a7b9-8ff2afeab9f0	0	否	2026-04-19 22:42:02.999351	2026-04-19 22:42:02.999351	f	\N
1	启用	1		primary	f	sys_common_status	3	6	9cd56103-41a7-4f0c-ac36-24b226675611	0	启用状态	2026-04-19 22:42:02.999355	2026-04-19 22:42:02.999355	f	\N
2	停用	0		danger	f	sys_common_status	3	7	9e5c98d0-cd33-4c63-9073-e7400bb2b334	0	停用状态	2026-04-19 22:42:02.999359	2026-04-19 22:42:02.999359	f	\N
1	通知	1	blue	warning	t	sys_notice_type	4	8	a62638ab-4019-40e1-8e97-17105a97f327	0	通知	2026-04-19 22:42:02.999363	2026-04-19 22:42:02.999363	f	\N
2	公告	2	orange	success	f	sys_notice_type	4	9	64709e65-5c52-4d01-a62f-547293c6b083	0	公告	2026-04-19 22:42:02.999367	2026-04-19 22:42:02.999367	f	\N
99	其他	0		info	f	sys_oper_type	5	10	5c405fa3-7eb2-4052-8c9c-7fcabe5ff364	0	其他操作	2026-04-19 22:42:02.999371	2026-04-19 22:42:02.999371	f	\N
1	新增	1		info	f	sys_oper_type	5	11	81939acf-65a6-4e04-b963-5c25a9ab23e2	0	新增操作	2026-04-19 22:42:02.999375	2026-04-19 22:42:02.999375	f	\N
2	修改	2		info	f	sys_oper_type	5	12	4f199351-5506-4e40-9f0c-dda0eb76ce3e	0	修改操作	2026-04-19 22:42:02.999379	2026-04-19 22:42:02.999379	f	\N
3	删除	3		danger	f	sys_oper_type	5	13	6d8035fb-3c27-45e3-8dc2-832eeeb0b5e7	0	删除操作	2026-04-19 22:42:02.999382	2026-04-19 22:42:02.999383	f	\N
4	分配权限	4		primary	f	sys_oper_type	5	14	f1cec927-a7ab-49f8-89e7-aa4522fc17ef	0	授权操作	2026-04-19 22:42:02.999386	2026-04-19 22:42:02.999387	f	\N
5	导出	5		warning	f	sys_oper_type	5	15	4945d268-512d-47dc-858d-78a1a293b049	0	导出操作	2026-04-19 22:42:02.99939	2026-04-19 22:42:02.999391	f	\N
6	导入	6		warning	f	sys_oper_type	5	16	09138733-1bda-4962-b555-3858b3eb2819	0	导入操作	2026-04-19 22:42:02.999394	2026-04-19 22:42:02.999395	f	\N
7	强退	7		danger	f	sys_oper_type	5	17	05085d20-9580-429e-9956-7ea49399756e	0	强退操作	2026-04-19 22:42:02.999398	2026-04-19 22:42:02.999399	f	\N
8	生成代码	8		warning	f	sys_oper_type	5	18	f0c0dfef-2a93-433d-8020-4cc60c4dd2eb	0	生成操作	2026-04-19 22:42:02.999402	2026-04-19 22:42:02.999403	f	\N
9	清空数据	9		danger	f	sys_oper_type	5	19	c19db15a-7639-4151-a289-9cafba05c46f	0	清空操作	2026-04-19 22:42:02.999406	2026-04-19 22:42:02.999406	f	\N
1	默认(Memory)	default		\N	t	sys_job_store	6	20	2fe8cf9c-1b3b-4d34-a22b-66dc9a1bd8ed	0	默认分组	2026-04-19 22:42:02.99941	2026-04-19 22:42:02.99941	f	\N
2	数据库(Sqlalchemy)	sqlalchemy		\N	f	sys_job_store	6	21	4267a90d-2e21-4b8d-836b-0d2638cb7dda	0	数据库分组	2026-04-19 22:42:02.999414	2026-04-19 22:42:02.999414	f	\N
3	数据库(Redis)	redis		\N	f	sys_job_store	6	22	1f6b519e-6d11-4902-a0f1-99e0772cdfac	0	reids分组	2026-04-19 22:42:02.999418	2026-04-19 22:42:02.999418	f	\N
1	线程池	default		\N	f	sys_job_executor	7	23	c02a0ccd-d53f-4b52-a8c9-e0ca24ed78c3	0	线程池	2026-04-19 22:42:02.999421	2026-04-19 22:42:02.999422	f	\N
2	进程池	processpool		\N	f	sys_job_executor	7	24	4fa07caa-2a63-4284-9b2e-7dd5240ebcbb	0	进程池	2026-04-19 22:42:02.999425	2026-04-19 22:42:02.999426	f	\N
1	演示函数	scheduler_test.job		\N	t	sys_job_function	8	25	52ce885e-402a-46ad-b12b-f2f203f20c29	0	演示函数	2026-04-19 22:42:02.999429	2026-04-19 22:42:02.99943	f	\N
1	指定日期(date)	date		\N	t	sys_job_trigger	9	26	98ccaf93-ecc3-46f0-917b-ca83b4427799	0	指定日期任务触发器	2026-04-19 22:42:02.999433	2026-04-19 22:42:02.999433	f	\N
2	间隔触发器(interval)	interval		\N	f	sys_job_trigger	9	27	a77088b5-8cad-4bb2-a602-3d6bb8e8ca22	0	间隔触发器任务触发器	2026-04-19 22:42:02.999437	2026-04-19 22:42:02.999437	f	\N
3	cron表达式	cron		\N	f	sys_job_trigger	9	28	f22198df-52ab-4980-84ec-67cea4fa1774	0	间隔触发器任务触发器	2026-04-19 22:42:02.999441	2026-04-19 22:42:02.999441	f	\N
1	默认(default)	default		\N	t	sys_list_class	10	29	4d963b1f-51f0-49c2-9cb6-ef0a7d68cc77	0	默认表格回显样式	2026-04-19 22:42:02.999444	2026-04-19 22:42:02.999445	f	\N
2	主要(primary)	primary		\N	f	sys_list_class	10	30	3f2cff52-178c-4758-a1d7-5c691b41dbb2	0	主要表格回显样式	2026-04-19 22:42:02.999448	2026-04-19 22:42:02.999449	f	\N
3	成功(success)	success		\N	f	sys_list_class	10	31	bd82f469-c619-4f1e-9818-044e981dfad4	0	成功表格回显样式	2026-04-19 22:42:02.999452	2026-04-19 22:42:02.999453	f	\N
4	信息(info)	info		\N	f	sys_list_class	10	32	1ebb93a1-41ad-41aa-8c18-37418c3705ab	0	信息表格回显样式	2026-04-19 22:42:02.999456	2026-04-19 22:42:02.999456	f	\N
5	警告(warning)	warning		\N	f	sys_list_class	10	33	dcbd457e-bb7c-4e4d-b880-756e2bec9620	0	警告表格回显样式	2026-04-19 22:42:02.99946	2026-04-19 22:42:02.99946	f	\N
6	危险(danger)	danger		\N	f	sys_list_class	10	34	aa232e39-6547-4c8c-82d4-c0a88e6c10f7	0	危险表格回显样式	2026-04-19 22:42:02.999464	2026-04-19 22:42:02.999464	f	\N
\.


--
-- Data for Name: sys_dict_type; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_dict_type (dict_name, dict_type, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time) FROM stdin;
用户性别	sys_user_sex	1	75fdde24-7093-4d14-8c1f-7e74b92159ba	0	用户性别列表	2026-04-19 22:42:02.994473	2026-04-19 22:42:02.994474	f	\N
系统是否	sys_yes_no	2	8d57dba8-8159-45f5-9bdc-5bded780e5a3	0	系统是否列表	2026-04-19 22:42:02.994479	2026-04-19 22:42:02.99448	f	\N
系统状态	sys_common_status	3	222258d6-a528-464c-9edc-3ffd3373be37	0	系统状态	2026-04-19 22:42:02.994483	2026-04-19 22:42:02.994484	f	\N
通知类型	sys_notice_type	4	e4e3f21a-7a9e-4ac8-94ad-aff207068e34	0	通知类型列表	2026-04-19 22:42:02.994487	2026-04-19 22:42:02.994488	f	\N
操作类型	sys_oper_type	5	dcb9dd48-a5df-4689-9d3c-37fcfea9007a	0	操作类型列表	2026-04-19 22:42:02.994491	2026-04-19 22:42:02.994492	f	\N
任务存储器	sys_job_store	6	a4e07725-1995-4eb6-a1b5-333657b46743	0	任务分组列表	2026-04-19 22:42:02.994495	2026-04-19 22:42:02.994496	f	\N
任务执行器	sys_job_executor	7	78988f08-4779-4507-8010-e6f63d8650e9	0	任务执行器列表	2026-04-19 22:42:02.994499	2026-04-19 22:42:02.9945	f	\N
任务函数	sys_job_function	8	6552fcce-627d-4d13-9912-f2061b9629a0	0	任务函数列表	2026-04-19 22:42:02.994503	2026-04-19 22:42:02.994504	f	\N
任务触发器	sys_job_trigger	9	1845c223-deb4-4c99-a88b-13640c754abc	0	任务触发器列表	2026-04-19 22:42:02.994507	2026-04-19 22:42:02.994508	f	\N
表格回显样式	sys_list_class	10	38e70397-806e-422f-9723-24787516d0eb	0	表格回显样式列表	2026-04-19 22:42:02.994511	2026-04-19 22:42:02.994512	f	\N
\.


--
-- Data for Name: sys_log; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_log (type, request_path, request_method, request_payload, request_ip, login_location, request_os, request_browser, response_code, response_json, process_time, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time, created_id, updated_id, deleted_id) FROM stdin;
\.


--
-- Data for Name: sys_menu; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_menu (name, type, "order", permission, icon, route_name, route_path, component_path, redirect, hidden, keep_alive, always_show, title, params, affix, parent_id, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time) FROM stdin;
仪表盘	1	1		client	Dashboard	/dashboard	\N	/dashboard/workplace	f	t	t	仪表盘	null	f	\N	1	449d61f1-4169-414d-9627-f35ba9995843	0	初始化数据	2026-04-19 22:42:02.956017	2026-04-19 22:42:02.95602	f	\N
系统管理	1	2	\N	system	System	/system	\N	/system/menu	f	t	f	系统管理	null	f	\N	2	c787dd31-1c8a-42cb-aab3-11a22146e5cf	0	初始化数据	2026-04-19 22:42:02.956025	2026-04-19 22:42:02.956026	f	\N
监控管理	1	3	\N	monitor	Monitor	/monitor	\N	/monitor/online	f	t	f	监控管理	null	f	\N	3	744f5df1-d60d-4988-bdd8-bfa57abf4edf	0	初始化数据	2026-04-19 22:42:02.95603	2026-04-19 22:42:02.956031	f	\N
接口管理	1	4	\N	document	Common	/common	\N	/common/docs	f	t	f	接口管理	null	f	\N	4	aecb3be6-7310-4500-8be1-ca55c60101f6	0	初始化数据	2026-04-19 22:42:02.956034	2026-04-19 22:42:02.956035	f	\N
代码管理	1	5	\N	code	Generator	/generator	\N	/generator/gencode	f	t	f	代码管理	null	f	\N	5	60b6d21f-f8ba-4558-8d04-48bb71e27174	0	代码管理	2026-04-19 22:42:02.956038	2026-04-19 22:42:02.956039	f	\N
应用管理	1	6	\N	el-icon-ShoppingBag	Application	/application	\N	/application/portal	f	t	f	应用管理	null	f	\N	6	63391b7d-3dea-4fcd-9a50-79a84f35530a	0	初始化数据	2026-04-19 22:42:02.956043	2026-04-19 22:42:02.956043	f	\N
AI管理	1	7	\N	el-icon-ChatLineSquare	AI	/ai	\N	/ai/chat	f	t	f	AI管理	null	f	\N	7	6a07c5d5-a07a-452c-aa3b-9a11b9c48a7d	0	AI管理	2026-04-19 22:42:02.956046	2026-04-19 22:42:02.956047	f	\N
任务管理	1	8	\N	el-icon-SetUp	Task	/task	\N	/task/cronjob/job	f	t	f	任务管理	null	f	\N	8	f6b45c45-fd6d-4569-87dc-9a32441f1386	0	任务管理	2026-04-19 22:42:02.95605	2026-04-19 22:42:02.956051	f	\N
案例管理	1	9	\N	menu	Example	/example	\N	/example/demo	f	t	f	案例管理	null	f	\N	9	3bd99c9d-c323-4f06-a091-8cfd2ce32c9c	0	案例管理	2026-04-19 22:42:02.956055	2026-04-19 22:42:02.956055	f	\N
工作台	2	1	dashboard:workplace:query	el-icon-PieChart	Workplace	/dashboard/workplace	dashboard/workplace	\N	f	t	f	工作台	null	f	1	10	7963593e-f883-4638-8be5-3eee907cca05	0	初始化数据	2026-04-19 22:42:02.959447	2026-04-19 22:42:02.959449	f	\N
菜单管理	2	1	module_system:menu:query	menu	Menu	/system/menu	module_system/menu/index	\N	f	t	f	菜单管理	null	f	2	11	2b91b068-4324-4bb2-b721-4797a0a5a7f4	0	初始化数据	2026-04-19 22:42:02.959454	2026-04-19 22:42:02.959455	f	\N
部门管理	2	2	module_system:dept:query	tree	Dept	/system/dept	module_system/dept/index	\N	f	t	f	部门管理	null	f	2	12	bca4bba1-b1e0-4ee2-8e47-767b5a3d318b	0	初始化数据	2026-04-19 22:42:02.959459	2026-04-19 22:42:02.959459	f	\N
岗位管理	2	3	module_system:position:query	el-icon-Coordinate	Position	/system/position	module_system/position/index	\N	f	t	f	岗位管理	null	f	2	13	5099390b-5a24-4bdd-858e-9781ce9ca6a7	0	初始化数据	2026-04-19 22:42:02.959463	2026-04-19 22:42:02.959464	f	\N
角色管理	2	4	module_system:role:query	role	Role	/system/role	module_system/role/index	\N	f	t	f	角色管理	null	f	2	14	411b65a4-1e34-492e-b8a4-9ec0edb9bdc8	0	初始化数据	2026-04-19 22:42:02.959468	2026-04-19 22:42:02.959468	f	\N
用户管理	2	5	module_system:user:query	el-icon-User	User	/system/user	module_system/user/index	\N	f	t	f	用户管理	null	f	2	15	ee0c377d-4d46-43d2-a1fe-b1d4ea70522a	0	初始化数据	2026-04-19 22:42:02.959472	2026-04-19 22:42:02.959472	f	\N
日志管理	2	6	module_system:log:query	el-icon-Aim	Log	/system/log	module_system/log/index	\N	f	t	f	日志管理	null	f	2	16	b4cafc22-7773-419a-ac54-af4326e360ba	0	初始化数据	2026-04-19 22:42:02.959476	2026-04-19 22:42:02.959476	f	\N
公告管理	2	7	module_system:notice:query	bell	Notice	/system/notice	module_system/notice/index	\N	f	t	f	公告管理	null	f	2	17	e0175dfb-9869-49c3-9b7c-003f39de3858	0	初始化数据	2026-04-19 22:42:02.95948	2026-04-19 22:42:02.95948	f	\N
参数管理	2	8	module_system:param:query	setting	Params	/system/param	module_system/param/index	\N	f	t	f	参数管理	null	f	2	18	223a430e-9dfd-4f2a-a3d0-2e079ac642a3	0	初始化数据	2026-04-19 22:42:02.959484	2026-04-19 22:42:02.959485	f	\N
字典管理	2	9	module_system:dict_type:query	dict	Dict	/system/dict	module_system/dict/index	\N	f	t	f	字典管理	null	f	2	19	09f3974b-0b9e-4830-b6e3-a0ce345f6979	0	初始化数据	2026-04-19 22:42:02.959488	2026-04-19 22:42:02.959489	f	\N
租户管理	2	10	module_system:tenant:query	el-icon-DataBoard	Tenant	/system/tenant	module_system/tenant/index	\N	f	t	f	租户管理	null	f	2	20	bab35c82-d00c-4297-8e69-afb691114093	0	初始化数据	2026-04-19 22:42:02.959493	2026-04-19 22:42:02.959493	f	\N
在线用户	2	1	module_monitor:online:query	el-icon-Headset	MonitorOnline	/monitor/online	module_monitor/online/index	\N	f	t	f	在线用户	null	f	3	21	7daa1d7c-e117-4df2-b941-97a724c84842	0	初始化数据	2026-04-19 22:42:02.959497	2026-04-19 22:42:02.959497	f	\N
服务器监控	2	2	module_monitor:server:query	el-icon-Odometer	MonitorServer	/monitor/server	module_monitor/server/index	\N	f	t	f	服务器监控	null	f	3	22	6055b13b-3d75-4ecb-af89-b9d5bcb64b7d	0	初始化数据	2026-04-19 22:42:02.959503	2026-04-19 22:42:02.959504	f	\N
缓存监控	2	3	module_monitor:cache:query	el-icon-Stopwatch	MonitorCache	/monitor/cache	module_monitor/cache/index	\N	f	t	f	缓存监控	null	f	3	23	fe5de323-cbc9-4a41-9ff0-3eda3212aa35	0	初始化数据	2026-04-19 22:42:02.959508	2026-04-19 22:42:02.959508	f	\N
文件管理	2	4	module_monitor:resource:query	el-icon-Files	Resource	/monitor/resource	module_monitor/resource/index	\N	f	t	f	文件管理	null	f	3	24	9714584d-9d1a-42c6-a94e-261a29ef2be3	0	初始化数据	2026-04-19 22:42:02.959512	2026-04-19 22:42:02.959512	f	\N
Swagger文档	4	1	module_common:docs:query	api	Docs	/common/docs	module_common/docs/index	\N	f	t	f	Swagger文档	null	f	4	25	af3fc7fb-0349-44ae-b94c-ec400050e9b9	0	初始化数据	2026-04-19 22:42:02.959516	2026-04-19 22:42:02.959516	f	\N
Redoc文档	4	2	module_common:redoc:query	el-icon-Document	Redoc	/common/redoc	module_common/redoc/index	\N	f	t	f	Redoc文档	null	f	4	26	aad94993-4d85-4310-9c31-65aaeb7bad0b	0	初始化数据	2026-04-19 22:42:02.95952	2026-04-19 22:42:02.95952	f	\N
LangJin文档	4	3	module_common:ljdoc:query	el-icon-Document	Ljdoc	/common/ljdoc	module_common/ljdoc/index	\N	f	t	f	LangJin文档	null	f	4	27	bef57ae6-3ee9-45fc-9bda-5cc7aaa44cd1	0	初始化数据	2026-04-19 22:42:02.959524	2026-04-19 22:42:02.959524	f	\N
代码生成	2	1	module_generator:gencode:query	code	GenCode	/generator/gencode	module_generator/gencode/index	\N	f	t	f	代码生成	null	f	5	28	3cbb0a1a-a2b8-4d4b-960b-66d8606e5135	0	代码生成	2026-04-19 22:42:02.959527	2026-04-19 22:42:02.959528	f	\N
插件市场	2	1	module_application:portal:query	el-icon-ShoppingCartFull	PortalApp	/application/portal	module_application/portal/index	\N	f	t	f	插件市场	null	f	6	29	fcfb6a4f-8dd0-477d-95cd-73515d019e91	0	初始化数据	2026-04-19 22:42:02.959531	2026-04-19 22:42:02.959532	f	\N
AI智能助手	2	1	module_ai:chat:query	el-icon-ChatDotRound	Chat	/ai/chat	module_ai/chat/index	\N	f	t	f	AI智能助手	null	f	7	30	3578b96b-aa16-49f3-92d6-357e59f74bf8	0	AI智能助手	2026-04-19 22:42:02.959535	2026-04-19 22:42:02.959536	f	\N
会话记忆	2	2	module_ai:chat:query	el-icon-ChatLineSquare	Memory	/ai/memory	module_ai/memory/index	\N	f	t	f	会话记忆	null	f	7	31	2896bdee-c7f9-470a-826a-9ad06cbb426b	0	会话记忆管理	2026-04-19 22:42:02.959539	2026-04-19 22:42:02.95954	f	\N
定时任务	1	1	\N	el-icon-Timer	Cronjob	/task/cronjob	\N	/task/cronjob/job	f	t	t	定时任务	null	f	8	32	14dfda3e-ab1d-4e59-89dc-a7562eef0dda	0	APScheduler 调度器与任务节点	2026-04-19 22:42:02.959543	2026-04-19 22:42:02.959544	f	\N
工作流	1	2	\N	el-icon-SetUp	WorkflowMgr	/task/workflow-mgr	\N	/task/workflow/definition	f	t	t	工作流	null	f	8	33	e40b7004-c565-428c-9654-ec735e21c781	0	流程编排与编排节点类型	2026-04-19 22:42:02.959547	2026-04-19 22:42:02.959547	f	\N
示例管理	2	1	module_example:demo:query	menu	Demo	/example/demo	module_example/demo/index	\N	f	t	f	示例管理	null	f	9	34	8a871ef2-2a35-4be2-9b32-e518444bf223	0	示例管理	2026-04-19 22:42:02.959551	2026-04-19 22:42:02.959551	f	\N
二级目录	1	2	\N	menu	DemoDir	/example/demo-group	\N	/example/demo-group/demo01	f	t	t	二级目录	null	f	9	35	93041183-ed14-4187-8b8f-16fd4401b0b5	0	二级目录（含三级菜单）	2026-04-19 22:42:02.959555	2026-04-19 22:42:02.959555	f	\N
创建菜单	3	1	module_system:menu:create	\N	\N	\N	\N	\N	f	t	f	创建菜单	null	f	11	36	2fa7a0dc-cf23-4121-bcee-17f8d9cde6d3	0	初始化数据	2026-04-19 22:42:02.965089	2026-04-19 22:42:02.965091	f	\N
修改菜单	3	2	module_system:menu:update	\N	\N	\N	\N	\N	f	t	f	修改菜单	null	f	11	37	6a3873ef-afe2-4bb5-9a17-995d50a34a38	0	初始化数据	2026-04-19 22:42:02.965096	2026-04-19 22:42:02.965097	f	\N
删除菜单	3	3	module_system:menu:delete	\N	\N	\N	\N	\N	f	t	f	删除菜单	null	f	11	38	061ecdce-33ad-4c1c-a2b2-0a00e851e537	0	初始化数据	2026-04-19 22:42:02.965101	2026-04-19 22:42:02.965102	f	\N
批量修改菜单状态	3	4	module_system:menu:patch	\N	\N	\N	\N	\N	f	t	f	批量修改菜单状态	null	f	11	39	7c9ab807-b828-4a44-aa50-501fe11863f3	0	初始化数据	2026-04-19 22:42:02.965106	2026-04-19 22:42:02.965106	f	\N
详情菜单	3	5	module_system:menu:detail	\N	\N	\N	\N	\N	f	t	f	详情菜单	null	f	11	40	430f93f7-ea42-4052-b41d-a983612276b8	0	初始化数据	2026-04-19 22:42:02.96511	2026-04-19 22:42:02.96511	f	\N
查询菜单	3	6	module_system:menu:query	\N	\N	\N	\N	\N	f	t	f	查询菜单	null	f	11	41	b16e2b77-169a-4859-bf4e-537b44a5818c	0	初始化数据	2026-04-19 22:42:02.965114	2026-04-19 22:42:02.965114	f	\N
创建部门	3	1	module_system:dept:create	\N	\N	\N	\N	\N	f	t	f	创建部门	null	f	12	42	5b09db67-fe5b-4094-a93f-e23d4321f21f	0	初始化数据	2026-04-19 22:42:02.965118	2026-04-19 22:42:02.965118	f	\N
修改部门	3	2	module_system:dept:update	\N	\N	\N	\N	\N	f	t	f	修改部门	null	f	12	43	c76ec374-73b9-4926-832b-e4aade056b88	0	初始化数据	2026-04-19 22:42:02.965122	2026-04-19 22:42:02.965122	f	\N
删除部门	3	3	module_system:dept:delete	\N	\N	\N	\N	\N	f	t	f	删除部门	null	f	12	44	3346dab8-e187-4777-9ed7-2d338fb2bd5d	0	初始化数据	2026-04-19 22:42:02.965126	2026-04-19 22:42:02.965126	f	\N
批量修改部门状态	3	4	module_system:dept:patch	\N	\N	\N	\N	\N	f	t	f	批量修改部门状态	null	f	12	45	85da5f0d-ff04-4722-af41-c9e1877f926b	0	初始化数据	2026-04-19 22:42:02.96513	2026-04-19 22:42:02.96513	f	\N
详情部门	3	5	module_system:dept:detail	\N	\N	\N	\N	\N	f	t	f	详情部门	null	f	12	46	c017193e-2739-4de4-a0fb-a31aec8b0cbc	0	初始化数据	2026-04-19 22:42:02.965134	2026-04-19 22:42:02.965134	f	\N
查询部门	3	6	module_system:dept:query	\N	\N	\N	\N	\N	f	t	f	查询部门	null	f	12	47	af738655-582b-40ad-8d2a-7ead131d2179	0	初始化数据	2026-04-19 22:42:02.965138	2026-04-19 22:42:02.965138	f	\N
创建岗位	3	1	module_system:position:create	\N	\N	\N	\N	\N	f	t	f	创建岗位	null	f	13	48	5568015c-3292-489f-88e5-d64fa71d940d	0	初始化数据	2026-04-19 22:42:02.965142	2026-04-19 22:42:02.965142	f	\N
修改岗位	3	2	module_system:position:update	\N	\N	\N	\N	\N	f	t	f	修改岗位	null	f	13	49	3fbbef8a-a108-44e3-abf3-75048d766bbd	0	初始化数据	2026-04-19 22:42:02.965146	2026-04-19 22:42:02.965146	f	\N
删除岗位	3	3	module_system:position:delete	\N	\N	\N	\N	\N	f	t	f	修改岗位	null	f	13	50	7da4a1dd-64fc-4507-a687-6d1b6dfab3a6	0	初始化数据	2026-04-19 22:42:02.96515	2026-04-19 22:42:02.96515	f	\N
批量修改岗位状态	3	4	module_system:position:patch	\N	\N	\N	\N	\N	f	t	f	批量修改岗位状态	null	f	13	51	2e7fbc65-c08e-4093-8f09-e30b8bcf7c09	0	初始化数据	2026-04-19 22:42:02.965156	2026-04-19 22:42:02.965157	f	\N
岗位导出	3	5	module_system:position:export	\N	\N	\N	\N	\N	f	t	f	岗位导出	null	f	13	52	c8ff0a53-f16f-40b6-a79e-92954daf5c32	0	初始化数据	2026-04-19 22:42:02.965161	2026-04-19 22:42:02.965161	f	\N
详情岗位	3	6	module_system:position:detail	\N	\N	\N	\N	\N	f	t	f	详情岗位	null	f	13	53	a9ec3ed8-aaf3-4d7a-a3d8-c161dd6ba728	0	初始化数据	2026-04-19 22:42:02.965165	2026-04-19 22:42:02.965165	f	\N
查询岗位	3	7	module_system:position:query	\N	\N	\N	\N	\N	f	t	f	查询岗位	null	f	13	54	587da349-d5b7-4e74-b6cf-ebec716ae933	0	初始化数据	2026-04-19 22:42:02.965169	2026-04-19 22:42:02.965169	f	\N
创建角色	3	1	module_system:role:create	\N	\N	\N	\N	\N	f	t	f	创建角色	null	f	14	55	15823f8f-b7b5-4d60-ad50-0565c8846da8	0	初始化数据	2026-04-19 22:42:02.965172	2026-04-19 22:42:02.965173	f	\N
修改角色	3	2	module_system:role:update	\N	\N	\N	\N	\N	f	t	f	修改角色	null	f	14	56	6c78f0a8-2dda-484a-a117-214bfa5009f9	0	初始化数据	2026-04-19 22:42:02.965176	2026-04-19 22:42:02.965177	f	\N
删除角色	3	3	module_system:role:delete	\N	\N	\N	\N	\N	f	t	f	删除角色	null	f	14	57	2f77174c-482a-46a5-aedf-29a0d85e0865	0	初始化数据	2026-04-19 22:42:02.96518	2026-04-19 22:42:02.965181	f	\N
批量修改角色状态	3	4	module_system:role:patch	\N	\N	\N	\N	\N	f	t	f	批量修改角色状态	null	f	14	58	8f79064c-c7ea-43f9-865b-0cad1f0eed44	0	初始化数据	2026-04-19 22:42:02.965184	2026-04-19 22:42:02.965185	f	\N
角色导出	3	5	module_system:role:export	\N	\N	\N	\N	\N	f	t	f	角色导出	null	f	14	59	d81675c0-ac08-418d-b099-483f7f3f857c	0	初始化数据	2026-04-19 22:42:02.965188	2026-04-19 22:42:02.965189	f	\N
详情角色	3	6	module_system:role:detail	\N	\N	\N	\N	\N	f	t	f	详情角色	null	f	14	60	b7628ffa-68a2-4918-ac7e-a210d45159a9	0	初始化数据	2026-04-19 22:42:02.965192	2026-04-19 22:42:02.965193	f	\N
查询角色	3	7	module_system:role:query	\N	\N	\N	\N	\N	f	t	f	查询角色	null	f	14	61	33a3b655-8ce1-4f49-88c9-f67512e5ad2f	0	初始化数据	2026-04-19 22:42:02.965196	2026-04-19 22:42:02.965196	f	\N
分配权限	3	8	module_system:role:permission	\N	\N	\N	\N	\N	f	t	f	分配权限	null	f	14	62	89bde31e-0aeb-4758-8443-cdd059527231	0	初始化数据	2026-04-19 22:42:02.9652	2026-04-19 22:42:02.9652	f	\N
创建用户	3	1	module_system:user:create	\N	\N	\N	\N	\N	f	t	f	创建用户	null	f	15	63	9256bd4c-e121-41c3-bfef-5e35de375943	0	初始化数据	2026-04-19 22:42:02.965204	2026-04-19 22:42:02.965204	f	\N
修改用户	3	2	module_system:user:update	\N	\N	\N	\N	\N	f	t	f	修改用户	null	f	15	64	d1dd32b5-4bae-495c-90b1-f12c3afdc717	0	初始化数据	2026-04-19 22:42:02.965208	2026-04-19 22:42:02.965208	f	\N
删除用户	3	3	module_system:user:delete	\N	\N	\N	\N	\N	f	t	f	删除用户	null	f	15	65	91209ea5-815a-4acc-a73b-04aee8452eb3	0	初始化数据	2026-04-19 22:42:02.965212	2026-04-19 22:42:02.965212	f	\N
批量修改用户状态	3	4	module_system:user:patch	\N	\N	\N	\N	\N	f	t	f	批量修改用户状态	null	f	15	66	cca980b2-c68c-40bc-b9ce-ae31aaaf43b7	0	初始化数据	2026-04-19 22:42:02.965216	2026-04-19 22:42:02.965216	f	\N
导出用户	3	5	module_system:user:export	\N	\N	\N	\N	\N	f	t	f	导出用户	null	f	15	67	83f38b88-fdfd-46ed-bbc0-247db7095eb0	0	初始化数据	2026-04-19 22:42:02.96522	2026-04-19 22:42:02.96522	f	\N
导入用户	3	6	module_system:user:import	\N	\N	\N	\N	\N	f	t	f	导入用户	null	f	15	68	001c9461-3d07-4c7d-ac27-cce889e75a67	0	初始化数据	2026-04-19 22:42:02.965224	2026-04-19 22:42:02.965224	f	\N
下载用户导入模板	3	7	module_system:user:download	\N	\N	\N	\N	\N	f	t	f	下载用户导入模板	null	f	15	69	1549f551-e868-466d-b0d4-ca1f0fa79194	0	初始化数据	2026-04-19 22:42:02.965228	2026-04-19 22:42:02.965228	f	\N
详情用户	3	8	module_system:user:detail	\N	\N	\N	\N	\N	f	t	f	详情用户	null	f	15	70	4ec9de3e-4486-45f3-a589-031f7a822d8c	0	初始化数据	2026-04-19 22:42:02.965232	2026-04-19 22:42:02.965232	f	\N
查询用户	3	9	module_system:user:query	\N	\N	\N	\N	\N	f	t	f	查询用户	null	f	15	71	e063bb5b-c8ae-42b0-bd98-00ba12bad039	0	初始化数据	2026-04-19 22:42:02.965236	2026-04-19 22:42:02.965236	f	\N
日志删除	3	1	module_system:log:delete	\N	\N	\N	\N	\N	f	t	f	日志删除	null	f	16	72	4c82b7e3-82f5-4991-af8a-f390dd6f7c89	0	初始化数据	2026-04-19 22:42:02.96524	2026-04-19 22:42:02.965241	f	\N
日志导出	3	2	module_system:log:export	\N	\N	\N	\N	\N	f	t	f	日志导出	null	f	16	73	0aa3d72c-e79a-4b2d-bedd-3a3d1b024539	0	初始化数据	2026-04-19 22:42:02.965244	2026-04-19 22:42:02.965245	f	\N
日志详情	3	3	module_system:log:detail	\N	\N	\N	\N	\N	f	t	f	日志详情	null	f	16	74	917a710b-6a6d-47fd-924b-898d9503d8d3	0	初始化数据	2026-04-19 22:42:02.965248	2026-04-19 22:42:02.965249	f	\N
查询日志	3	4	module_system:log:query	\N	\N	\N	\N	\N	f	t	f	查询日志	null	f	16	75	9a8e49df-9de0-4431-be44-995510ceb663	0	初始化数据	2026-04-19 22:42:02.965252	2026-04-19 22:42:02.965253	f	\N
公告创建	3	1	module_system:notice:create	\N	\N	\N	\N	\N	f	t	f	公告创建	null	f	17	76	217413cf-285e-4ade-8f7a-326d836e2320	0	初始化数据	2026-04-19 22:42:02.965256	2026-04-19 22:42:02.965257	f	\N
公告修改	3	2	module_system:notice:update	\N	\N	\N	\N	\N	f	t	f	修改用户	null	f	17	77	03aea49a-e562-44c8-ab14-eab2b44007d8	0	初始化数据	2026-04-19 22:42:02.96526	2026-04-19 22:42:02.965261	f	\N
公告删除	3	3	module_system:notice:delete	\N	\N	\N	\N	\N	f	t	f	公告删除	null	f	17	78	99d1bb6d-2276-4b43-8ec1-e07327ddf8e4	0	初始化数据	2026-04-19 22:42:02.965264	2026-04-19 22:42:02.965265	f	\N
公告导出	3	4	module_system:notice:export	\N	\N	\N	\N	\N	f	t	f	公告导出	null	f	17	79	15937f08-6e33-4232-8f63-bc660d1e5572	0	初始化数据	2026-04-19 22:42:02.965268	2026-04-19 22:42:02.965269	f	\N
公告批量修改状态	3	5	module_system:notice:patch	\N	\N	\N	\N	\N	f	t	f	公告批量修改状态	null	f	17	80	22cc5d4c-723f-4dff-9e2a-0eecf7ce309b	0	初始化数据	2026-04-19 22:42:02.965272	2026-04-19 22:42:02.965272	f	\N
公告详情	3	6	module_system:notice:detail	\N	\N	\N	\N	\N	f	t	f	公告详情	null	f	17	81	75e65e3f-ed22-48b3-adf3-26ffe90687ea	0	初始化数据	2026-04-19 22:42:02.965276	2026-04-19 22:42:02.965276	f	\N
查询公告	3	5	module_system:notice:query	\N	\N	\N	\N	\N	f	t	f	查询公告	null	f	17	82	a05363bc-ff85-40a7-b04c-b1450635c16f	0	初始化数据	2026-04-19 22:42:02.96528	2026-04-19 22:42:02.96528	f	\N
创建参数	3	1	module_system:param:create	\N	\N	\N	\N	\N	f	t	f	创建参数	null	f	18	83	3252b09c-f21d-4f38-b27e-9152e07930e2	0	初始化数据	2026-04-19 22:42:02.965284	2026-04-19 22:42:02.965284	f	\N
修改参数	3	2	module_system:param:update	\N	\N	\N	\N	\N	f	t	f	修改参数	null	f	18	84	b10dd7e7-6eac-4262-a491-c4d0e5762072	0	初始化数据	2026-04-19 22:42:02.965288	2026-04-19 22:42:02.965288	f	\N
删除参数	3	3	module_system:param:delete	\N	\N	\N	\N	\N	f	t	f	删除参数	null	f	18	85	e88a2c7b-b7cc-4339-b8cf-07089a22adf0	0	初始化数据	2026-04-19 22:42:02.965292	2026-04-19 22:42:02.965292	f	\N
导出参数	3	4	module_system:param:export	\N	\N	\N	\N	\N	f	t	f	导出参数	null	f	18	86	40c2a2c9-4fb1-4512-a496-5c870801a97f	0	初始化数据	2026-04-19 22:42:02.965295	2026-04-19 22:42:02.965296	f	\N
参数上传	3	5	module_system:param:upload	\N	\N	\N	\N	\N	f	t	f	参数上传	null	f	18	87	18001f1b-3e76-4231-9846-f3aa4d997b1d	0	初始化数据	2026-04-19 22:42:02.965299	2026-04-19 22:42:02.9653	f	\N
参数详情	3	6	module_system:param:detail	\N	\N	\N	\N	\N	f	t	f	参数详情	null	f	18	88	48e647b3-57bb-4fb2-83bc-9d575a233f0b	0	初始化数据	2026-04-19 22:42:02.965303	2026-04-19 22:42:02.965304	f	\N
查询参数	3	7	module_system:param:query	\N	\N	\N	\N	\N	f	t	f	查询参数	null	f	18	89	4d001545-e38e-48ac-9796-3eb7864046b3	0	初始化数据	2026-04-19 22:42:02.965307	2026-04-19 22:42:02.965308	f	\N
创建字典类型	3	1	module_system:dict_type:create	\N	\N	\N	\N	\N	f	t	f	创建字典类型	null	f	19	90	5fd8fb2d-8992-402f-802e-43c03ea80f47	0	初始化数据	2026-04-19 22:42:02.965311	2026-04-19 22:42:02.965312	f	\N
修改字典类型	3	2	module_system:dict_type:update	\N	\N	\N	\N	\N	f	t	f	修改字典类型	null	f	19	91	8bdc7a63-1ad1-4f76-ab5e-ca2b2723e4c1	0	初始化数据	2026-04-19 22:42:02.965315	2026-04-19 22:42:02.965316	f	\N
删除字典类型	3	3	module_system:dict_type:delete	\N	\N	\N	\N	\N	f	t	f	删除字典类型	null	f	19	92	f549f5a8-1c85-4dd9-8e03-307cfbacad3f	0	初始化数据	2026-04-19 22:42:02.965319	2026-04-19 22:42:02.96532	f	\N
导出字典类型	3	4	module_system:dict_type:export	\N	\N	\N	\N	\N	f	t	f	导出字典类型	null	f	19	93	8c8d8d13-e764-45ad-994b-2d23daf621c8	0	初始化数据	2026-04-19 22:42:02.965323	2026-04-19 22:42:02.965324	f	\N
批量修改字典状态	3	5	module_system:dict_type:patch	\N	\N	\N	\N	\N	f	t	f	导出字典类型	null	f	19	94	8e4fcdbd-8697-48df-bb82-056b7a1aaaab	0	初始化数据	2026-04-19 22:42:02.965327	2026-04-19 22:42:02.965328	f	\N
字典数据查询	3	6	module_system:dict_data:query	\N	\N	\N	\N	\N	f	t	f	字典数据查询	null	f	19	95	b023e493-0ba3-4fd9-a37f-283e79278b36	0	初始化数据	2026-04-19 22:42:02.965331	2026-04-19 22:42:02.965332	f	\N
创建字典数据	3	7	module_system:dict_data:create	\N	\N	\N	\N	\N	f	t	f	创建字典数据	null	f	19	96	6589feca-c9a5-442e-aa17-0f2e44ca50e5	0	初始化数据	2026-04-19 22:42:02.965335	2026-04-19 22:42:02.965335	f	\N
修改字典数据	3	8	module_system:dict_data:update	\N	\N	\N	\N	\N	f	t	f	修改字典数据	null	f	19	97	2ae6e1a5-f8fc-49c5-a906-ab3f52e918a1	0	初始化数据	2026-04-19 22:42:02.965339	2026-04-19 22:42:02.965339	f	\N
删除字典数据	3	9	module_system:dict_data:delete	\N	\N	\N	\N	\N	f	t	f	删除字典数据	null	f	19	98	ad5850f9-ec6f-43e7-a05a-72d194348f8d	0	初始化数据	2026-04-19 22:42:02.965343	2026-04-19 22:42:02.965343	f	\N
导出字典数据	3	10	module_system:dict_data:export	\N	\N	\N	\N	\N	f	t	f	导出字典数据	null	f	19	99	dd04991a-be79-44b6-a3f1-00d59d3c1c90	0	初始化数据	2026-04-19 22:42:02.965347	2026-04-19 22:42:02.965347	f	\N
批量修改字典数据状态	3	11	module_system:dict_data:patch	\N	\N	\N	\N	\N	f	t	f	批量修改字典数据状态	null	f	19	100	a46c36f5-85f4-45bd-885f-5a89e52e7649	0	初始化数据	2026-04-19 22:42:02.965351	2026-04-19 22:42:02.965351	f	\N
详情字典类型	3	12	module_system:dict_type:detail	\N	\N	\N	\N	\N	f	t	f	详情字典类型	null	f	19	101	ef60d94a-d57e-46df-80f5-2c298fcd1e11	0	初始化数据	2026-04-19 22:42:02.965355	2026-04-19 22:42:02.965355	f	\N
查询字典类型	3	13	module_system:dict_type:query	\N	\N	\N	\N	\N	f	t	f	查询字典类型	null	f	19	102	bbc5fb74-8e46-49e6-8ad9-9ae3f627ec79	0	初始化数据	2026-04-19 22:42:02.965359	2026-04-19 22:42:02.965359	f	\N
详情字典数据	3	14	module_system:dict_data:detail	\N	\N	\N	\N	\N	f	t	f	详情字典数据	null	f	19	103	39d70db5-1eef-4abd-abdb-39bea5027b8b	0	初始化数据	2026-04-19 22:42:02.965362	2026-04-19 22:42:02.965363	f	\N
创建租户	3	1	module_system:tenant:create	\N	\N	\N	\N	\N	f	t	f	创建租户	null	f	20	104	76537eb8-5249-4316-b42c-0941c5b968af	0	初始化数据	2026-04-19 22:42:02.965366	2026-04-19 22:42:02.965367	f	\N
修改租户	3	2	module_system:tenant:update	\N	\N	\N	\N	\N	f	t	f	修改租户	null	f	20	105	4581c762-350c-48e8-bb77-eeea84f3e927	0	初始化数据	2026-04-19 22:42:02.96537	2026-04-19 22:42:02.965371	f	\N
删除租户	3	3	module_system:tenant:delete	\N	\N	\N	\N	\N	f	t	f	删除租户	null	f	20	106	cba3082a-8bc5-43c4-a39c-be3a0ed06a3f	0	初始化数据	2026-04-19 22:42:02.965374	2026-04-19 22:42:02.965375	f	\N
批量修改租户状态	3	4	module_system:tenant:patch	\N	\N	\N	\N	\N	f	t	f	批量修改租户状态	null	f	20	107	901ded95-4cac-4524-b9a1-593b6a284f2c	0	初始化数据	2026-04-19 22:42:02.965378	2026-04-19 22:42:02.965379	f	\N
租户详情	3	5	module_system:tenant:query	\N	\N	\N	\N	\N	f	t	f	租户详情	null	f	20	108	521f76f9-ea69-4a7c-b9d6-d45790057242	0	初始化数据	2026-04-19 22:42:02.965382	2026-04-19 22:42:02.965383	f	\N
查询租户	3	6	module_system:tenant:query	\N	\N	\N	\N	\N	f	t	f	查询租户	null	f	20	109	a0a37dad-25be-4522-9ee6-faa0e6213f1e	0	初始化数据	2026-04-19 22:42:02.965386	2026-04-19 22:42:02.965386	f	\N
在线用户强制下线	3	1	module_monitor:online:delete	\N	\N	\N	\N	\N	f	t	f	在线用户强制下线	null	f	21	110	31e1e33f-27e8-4f0d-9d2a-ee933f38baf9	0	初始化数据	2026-04-19 22:42:02.96539	2026-04-19 22:42:02.96539	f	\N
清除缓存	3	1	module_monitor:cache:delete	\N	\N	\N	\N	\N	f	t	f	清除缓存	null	f	23	111	46ec894e-50e5-4843-aff3-3116e97b66c1	0	初始化数据	2026-04-19 22:42:02.965394	2026-04-19 22:42:02.965394	f	\N
文件上传	3	1	module_monitor:resource:upload	\N	\N	\N	\N	\N	f	t	f	文件上传	null	f	24	112	c11326d9-b71b-4e25-92a2-58c379a98731	0	初始化数据	2026-04-19 22:42:02.965398	2026-04-19 22:42:02.965398	f	\N
文件下载	3	2	module_monitor:resource:download	\N	\N	\N	\N	\N	f	t	f	文件下载	null	f	24	113	fc3260bc-f1b6-4a1a-ab5b-fc57507c3ddd	0	初始化数据	2026-04-19 22:42:02.965402	2026-04-19 22:42:02.965402	f	\N
文件删除	3	3	module_monitor:resource:delete	\N	\N	\N	\N	\N	f	t	f	文件删除	null	f	24	114	6e2e1c03-ba15-41b0-a8d2-cda161d53df2	0	初始化数据	2026-04-19 22:42:02.965406	2026-04-19 22:42:02.965406	f	\N
文件移动	3	4	module_monitor:resource:move	\N	\N	\N	\N	\N	f	t	f	文件移动	null	f	24	115	45952718-2307-40cd-89cb-d39e4db3a4bb	0	初始化数据	2026-04-19 22:42:02.96541	2026-04-19 22:42:02.96541	f	\N
文件复制	3	5	module_monitor:resource:copy	\N	\N	\N	\N	\N	f	t	f	文件复制	null	f	24	116	38e312c2-01df-4608-9bd0-12d174eae6c3	0	初始化数据	2026-04-19 22:42:02.965414	2026-04-19 22:42:02.965414	f	\N
文件重命名	3	6	module_monitor:resource:rename	\N	\N	\N	\N	\N	f	t	f	文件重命名	null	f	24	117	1dc6a690-db26-4586-b748-80fc998dce96	0	初始化数据	2026-04-19 22:42:02.965418	2026-04-19 22:42:02.965418	f	\N
创建目录	3	7	module_monitor:resource:create_dir	\N	\N	\N	\N	\N	f	t	f	创建目录	null	f	24	118	d327780c-5d15-4489-b297-85532c63e713	0	初始化数据	2026-04-19 22:42:02.965421	2026-04-19 22:42:02.965422	f	\N
导出文件列表	3	9	module_monitor:resource:export	\N	\N	\N	\N	\N	f	t	f	导出文件列表	null	f	24	119	ac84e7d4-030d-4099-b027-4df14eabfcd7	0	初始化数据	2026-04-19 22:42:02.965425	2026-04-19 22:42:02.965426	f	\N
查询代码生成业务表列表	3	1	module_generator:gencode:query	\N	\N	\N	\N	\N	f	t	f	查询代码生成业务表列表	null	f	28	120	e3e5e61c-cf59-4946-9112-c2a5f580d54b	0	查询代码生成业务表列表	2026-04-19 22:42:02.965429	2026-04-19 22:42:02.96543	f	\N
创建表结构	3	2	module_generator:gencode:create	\N	\N	\N	\N	\N	f	t	f	创建表结构	null	f	28	121	0a77ba8b-b0da-4b6d-97f4-f93f0ba702b8	0	创建表结构	2026-04-19 22:42:02.965433	2026-04-19 22:42:02.965434	f	\N
编辑业务表信息	3	3	module_generator:gencode:update	\N	\N	\N	\N	\N	f	t	f	编辑业务表信息	null	f	28	122	dd260310-42dc-4239-9f6c-35f63a0368e1	0	编辑业务表信息	2026-04-19 22:42:02.965437	2026-04-19 22:42:02.965438	f	\N
删除业务表信息	3	4	module_generator:gencode:delete	\N	\N	\N	\N	\N	f	t	f	删除业务表信息	null	f	28	123	11a31bfb-4853-4971-b1bd-94b21d023ffd	0	删除业务表信息	2026-04-19 22:42:02.965441	2026-04-19 22:42:02.965442	f	\N
导入表结构	3	5	module_generator:gencode:import	\N	\N	\N	\N	\N	f	t	f	导入表结构	null	f	28	124	2d8f9ac8-4059-4fe2-a188-9cb4af876c50	0	导入表结构	2026-04-19 22:42:02.965445	2026-04-19 22:42:02.965445	f	\N
批量生成代码	3	6	module_generator:gencode:operate	\N	\N	\N	\N	\N	f	t	f	批量生成代码	null	f	28	125	6eb031d9-cb06-4c3d-999b-ee97def041db	0	批量生成代码	2026-04-19 22:42:02.965449	2026-04-19 22:42:02.965449	f	\N
生成代码到指定路径	3	7	module_generator:gencode:code	\N	\N	\N	\N	\N	f	t	f	生成代码到指定路径	null	f	28	126	0026dc6a-8069-4310-84fe-467bcb6f04e2	0	生成代码到指定路径	2026-04-19 22:42:02.965453	2026-04-19 22:42:02.965454	f	\N
查询数据库表列表	3	8	module_generator:dblist:query	\N	\N	\N	\N	\N	f	t	f	查询数据库表列表	null	f	28	127	810b16e7-7e05-4243-9fa9-bddf16062c68	0	查询数据库表列表	2026-04-19 22:42:02.965457	2026-04-19 22:42:02.965458	f	\N
同步数据库	3	9	module_generator:db:sync	\N	\N	\N	\N	\N	f	t	f	同步数据库	null	f	28	128	9b53166e-7b94-4662-ace0-7813ccca42ac	0	同步数据库	2026-04-19 22:42:02.965461	2026-04-19 22:42:02.965462	f	\N
创建插件	3	1	module_application:portal:create	\N	\N	\N	\N	\N	f	t	f	创建插件	null	f	29	129	4a4deb51-b020-429a-b570-ce8b4a612e7e	0	初始化数据	2026-04-19 22:42:02.965465	2026-04-19 22:42:02.965466	f	\N
修改插件	3	2	module_application:portal:update	\N	\N	\N	\N	\N	f	t	f	修改插件	null	f	29	130	d3b082b3-d9ee-44bc-8339-47249689c309	0	初始化数据	2026-04-19 22:42:02.965469	2026-04-19 22:42:02.96547	f	\N
删除插件	3	3	module_application:portal:delete	\N	\N	\N	\N	\N	f	t	f	删除插件	null	f	29	131	feb68811-c634-414c-a8ce-5aeb9ccabee2	0	初始化数据	2026-04-19 22:42:02.965475	2026-04-19 22:42:02.965475	f	\N
批量修改插件状态	3	4	module_application:portal:patch	\N	\N	\N	\N	\N	f	t	f	批量修改应用状态	null	f	29	132	f21da67f-d792-4d42-95cd-0fe5f464281f	0	初始化数据	2026-04-19 22:42:02.965479	2026-04-19 22:42:02.96548	f	\N
详情插件	3	5	module_application:portal:detail	\N	\N	\N	\N	\N	f	t	f	详情插件	null	f	29	133	c37029c2-5e91-4533-baad-25a182567c26	0	初始化数据	2026-04-19 22:42:02.965483	2026-04-19 22:42:02.965484	f	\N
查询插件	3	6	module_application:portal:query	\N	\N	\N	\N	\N	f	t	f	查询插件	null	f	29	134	20f635cf-ac85-470b-b78b-45a5d2f2a829	0	查询插件	2026-04-19 22:42:02.965487	2026-04-19 22:42:02.965488	f	\N
AI对话	3	1	module_ai:chat:ws	\N	\N	\N	\N	\N	f	t	f	AI对话	null	f	30	135	5f4dc95b-f120-486c-8981-da9274101189	0	AI对话	2026-04-19 22:42:02.965491	2026-04-19 22:42:02.965492	f	\N
查询会话	3	2	module_ai:chat:query	\N	\N	\N	\N	\N	f	t	f	查询会话	null	f	30	136	26cfbe61-f41f-479f-a8e8-fe0d60192f1a	0	查询会话	2026-04-19 22:42:02.965495	2026-04-19 22:42:02.965496	f	\N
会话详情	3	3	module_ai:chat:detail	\N	\N	\N	\N	\N	f	t	f	会话详情	null	f	30	137	cd555788-ec9c-4a60-884e-4ae7fd762c83	0	会话详情	2026-04-19 22:42:02.965499	2026-04-19 22:42:02.9655	f	\N
创建会话	3	4	module_ai:chat:create	\N	\N	\N	\N	\N	f	t	f	创建会话	null	f	30	138	d1606c5b-26ac-4d27-89f6-a79777da53ca	0	创建会话	2026-04-19 22:42:02.965503	2026-04-19 22:42:02.965504	f	\N
更新会话	3	5	module_ai:chat:update	\N	\N	\N	\N	\N	f	t	f	更新会话	null	f	30	139	7c06d6f1-497a-461e-b426-d1b3758eb314	0	更新会话	2026-04-19 22:42:02.965507	2026-04-19 22:42:02.965508	f	\N
删除会话	3	6	module_ai:chat:delete	\N	\N	\N	\N	\N	f	t	f	删除会话	null	f	30	140	30469241-b68b-43c2-bfa2-1139b264581e	0	删除会话	2026-04-19 22:42:02.965511	2026-04-19 22:42:02.965512	f	\N
查询会话记忆	3	1	module_ai:chat:query	\N	\N	\N	\N	\N	f	t	f	查询会话记忆	null	f	31	141	5902f5d7-9dac-4cd7-861e-7e72570beacf	0	查询会话记忆	2026-04-19 22:42:02.965515	2026-04-19 22:42:02.965516	f	\N
会话记忆详情	3	2	module_ai:chat:detail	\N	\N	\N	\N	\N	f	t	f	会话记忆详情	null	f	31	142	17c05678-2197-490c-94c1-3648bf7da5e6	0	会话记忆详情	2026-04-19 22:42:02.965519	2026-04-19 22:42:02.965519	f	\N
删除会话记忆	3	3	module_ai:chat:delete	\N	\N	\N	\N	\N	f	t	f	删除会话记忆	null	f	31	143	f0fdb7f6-0cd1-414e-95b6-5359382a4f2b	0	删除会话记忆	2026-04-19 22:42:02.965523	2026-04-19 22:42:02.965523	f	\N
调度器监控	2	1	module_task:cronjob:job:query	el-icon-DataLine	Job	/task/cronjob/job	module_task/cronjob/job/index	\N	f	t	f	调度器监控	null	f	32	144	a10ef4c8-864c-4109-8ae9-0482b3fb6dda	0	调度器监控	2026-04-19 22:42:02.965527	2026-04-19 22:42:02.965527	f	\N
节点管理	2	2	module_task:cronjob:node:query	el-icon-Postcard	Node	/task/cronjob/node	module_task/cronjob/node/index	\N	f	t	f	节点管理	null	f	32	145	cbf78a6e-a0c0-4eb5-b399-57ed245dc8c0	0	节点管理	2026-04-19 22:42:02.965531	2026-04-19 22:42:02.965531	f	\N
流程编排	2	1	module_task:workflow:definition:query	el-icon-SetUp	Workflow	/task/workflow/definition	module_task/workflow/definition/index	\N	f	t	f	流程编排	null	f	33	146	2d9ff241-5306-42fa-ac3d-a721da64f275	0	Vue Flow 画布与发布执行	2026-04-19 22:42:02.965535	2026-04-19 22:42:02.965535	f	\N
编排节点类型	2	2	module_task:workflow:node-type:query	el-icon-Grid	WorkflowNodeType	/task/workflow/node-type	module_task/workflow/node-type/index	\N	f	t	f	编排节点类型	null	f	33	147	ee09056e-424b-4ec3-b07b-797ad793fe88	0	画布节点类型与 Prefect 执行逻辑	2026-04-19 22:42:02.965539	2026-04-19 22:42:02.965539	f	\N
创建示例	3	1	module_example:demo:create	\N	\N	\N	\N	\N	f	t	f	创建示例	null	f	34	148	0d645885-4ff6-4d68-b62e-e1e335890515	0	初始化数据	2026-04-19 22:42:02.965543	2026-04-19 22:42:02.965543	f	\N
更新示例	3	2	module_example:demo:update	\N	\N	\N	\N	\N	f	t	f	更新示例	null	f	34	149	6e465345-a021-41d9-9a14-4ec93306aef8	0	初始化数据	2026-04-19 22:42:02.965547	2026-04-19 22:42:02.965547	f	\N
删除示例	3	3	module_example:demo:delete	\N	\N	\N	\N	\N	f	t	f	删除示例	null	f	34	150	8ccbd848-ad9c-43ce-8b4b-252606a12382	0	初始化数据	2026-04-19 22:42:02.965551	2026-04-19 22:42:02.965551	f	\N
批量修改示例状态	3	4	module_example:demo:patch	\N	\N	\N	\N	\N	f	t	f	批量修改示例状态	null	f	34	151	791fbe7f-cdce-4611-8151-0a9ede7a6353	0	初始化数据	2026-04-19 22:42:02.965555	2026-04-19 22:42:02.965555	f	\N
导出示例	3	5	module_example:demo:export	\N	\N	\N	\N	\N	f	t	f	导出示例	null	f	34	152	0bb9a1ae-e77f-455b-b539-7ec0b04baf7a	0	初始化数据	2026-04-19 22:42:02.965558	2026-04-19 22:42:02.965559	f	\N
导入示例	3	6	module_example:demo:import	\N	\N	\N	\N	\N	f	t	f	导入示例	null	f	34	153	dca8ff6e-ba4a-49d1-8bf9-e1673a76c4d7	0	初始化数据	2026-04-19 22:42:02.965562	2026-04-19 22:42:02.965563	f	\N
下载导入示例模版	3	7	module_example:demo:download	\N	\N	\N	\N	\N	f	t	f	下载导入示例模版	null	f	34	154	8fa28989-cfd3-4b4a-ae6a-8cbdc443121c	0	初始化数据	2026-04-19 22:42:02.965566	2026-04-19 22:42:02.965567	f	\N
详情示例	3	8	module_example:demo:detail	\N	\N	\N	\N	\N	f	t	f	详情示例	null	f	34	155	4168f0d6-c80e-4fbc-a44d-bf4c750c5276	0	初始化数据	2026-04-19 22:42:02.96557	2026-04-19 22:42:02.965571	f	\N
查询示例	3	9	module_example:demo:query	\N	\N	\N	\N	\N	f	t	f	查询示例	null	f	34	156	ca1ff3c5-8e85-476c-ba70-9eb5da91fe58	0	初始化数据	2026-04-19 22:42:02.965574	2026-04-19 22:42:02.965575	f	\N
三级菜单	2	1	module_example:demo01:query	menu	Demo01	/example/demo-group/demo01	module_example/demo01/index	\N	f	t	f	三级菜单	null	f	35	157	9bebbd7e-75b7-45c3-903a-2ed771561d0a	0	示例01管理	2026-04-19 22:42:02.965578	2026-04-19 22:42:02.965579	f	\N
查询调度器	3	1	module_task:cronjob:job:query	\N	\N	\N	\N	\N	f	t	f	查询调度器	null	f	144	158	84a15cf1-49cd-407b-82b4-fd73129e2462	0	查询调度器	2026-04-19 22:42:02.973483	2026-04-19 22:42:02.973485	f	\N
控制调度器	3	2	module_task:cronjob:job:scheduler	\N	\N	\N	\N	\N	f	t	f	控制调度器	null	f	144	159	ee71a672-c94e-43ef-8bda-13733224c37f	0	控制调度器	2026-04-19 22:42:02.97349	2026-04-19 22:42:02.97349	f	\N
操作任务	3	3	module_task:cronjob:job:task	\N	\N	\N	\N	\N	f	t	f	操作任务	null	f	144	160	c399aa93-59ad-4e4b-a5ee-5b58c0bf0d3c	0	操作任务	2026-04-19 22:42:02.973494	2026-04-19 22:42:02.973495	f	\N
删除执行日志	3	4	module_task:cronjob:job:delete	\N	\N	\N	\N	\N	f	t	f	删除执行日志	null	f	144	161	1d960601-4168-4299-92f9-3f4c7090f84c	0	删除执行日志	2026-04-19 22:42:02.973498	2026-04-19 22:42:02.973499	f	\N
详情执行日志	3	5	module_task:cronjob:job:detail	\N	\N	\N	\N	\N	f	t	f	详情执行日志	null	f	144	162	850cee46-f345-448e-958d-572ecbd08e0e	0	详情执行日志	2026-04-19 22:42:02.973502	2026-04-19 22:42:02.973503	f	\N
创建节点	3	1	module_task:cronjob:node:create	\N	\N	\N	\N	\N	f	t	f	创建节点	null	f	145	163	de06736e-a68d-45eb-b106-88393a77a756	0	创建节点	2026-04-19 22:42:02.973506	2026-04-19 22:42:02.973507	f	\N
调试节点	3	2	module_task:cronjob:node:execute	\N	\N	\N	\N	\N	f	t	f	调试节点	null	f	145	164	6af3ee72-da64-40e5-8f2c-c13015c2bc26	0	调试节点	2026-04-19 22:42:02.97351	2026-04-19 22:42:02.973511	f	\N
修改节点	3	3	module_task:cronjob:node:update	\N	\N	\N	\N	\N	f	t	f	修改节点	null	f	145	165	12930872-8d02-4e78-8232-7ea90ae7e10e	0	修改节点	2026-04-19 22:42:02.973514	2026-04-19 22:42:02.973515	f	\N
删除节点	3	4	module_task:cronjob:node:delete	\N	\N	\N	\N	\N	f	t	f	删除节点	null	f	145	166	a02e3a5c-a282-4e28-84a6-72dea1a2fa13	0	删除节点	2026-04-19 22:42:02.973518	2026-04-19 22:42:02.973519	f	\N
详情节点	3	5	module_task:cronjob:node:detail	\N	\N	\N	\N	\N	f	t	f	详情节点	null	f	145	167	83215170-d770-4e43-951e-4b8681ca2f2b	0	详情节点	2026-04-19 22:42:02.973522	2026-04-19 22:42:02.973523	f	\N
查询节点	3	6	module_task:cronjob:node:query	\N	\N	\N	\N	\N	f	t	f	查询节点	null	f	145	168	f0f8b249-6966-4e10-9ef8-402c99fd51ec	0	查询节点	2026-04-19 22:42:02.973526	2026-04-19 22:42:02.973527	f	\N
创建流程	3	1	module_task:workflow:definition:create	\N	\N	\N	\N	\N	f	t	f	创建流程	null	f	146	169	92a472a3-4a25-4577-8a89-12f054361478	0	创建流程	2026-04-19 22:42:02.97353	2026-04-19 22:42:02.97353	f	\N
执行流程	3	2	module_task:workflow:definition:execute	\N	\N	\N	\N	\N	f	t	f	执行流程	null	f	146	170	f3519a50-43f0-414a-b8d6-54787506e602	0	执行流程	2026-04-19 22:42:02.973534	2026-04-19 22:42:02.973534	f	\N
修改流程	3	3	module_task:workflow:definition:update	\N	\N	\N	\N	\N	f	t	f	修改流程	null	f	146	171	43166f8d-053c-4512-bffb-0503ab357ca4	0	修改流程	2026-04-19 22:42:02.973538	2026-04-19 22:42:02.973538	f	\N
删除流程	3	4	module_task:workflow:definition:delete	\N	\N	\N	\N	\N	f	t	f	删除流程	null	f	146	172	f0278c47-6903-4c35-bd58-09f24b88026a	0	删除流程	2026-04-19 22:42:02.973541	2026-04-19 22:42:02.973542	f	\N
详情流程	3	5	module_task:workflow:definition:detail	\N	\N	\N	\N	\N	f	t	f	详情流程	null	f	146	173	9eaefa25-dbc3-450e-8e82-6885de805cc9	0	详情流程	2026-04-19 22:42:02.973545	2026-04-19 22:42:02.973546	f	\N
查询流程	3	6	module_task:workflow:definition:query	\N	\N	\N	\N	\N	f	t	f	查询流程	null	f	146	174	dedcb1d6-2740-4b05-a9f1-a422fb7cb17e	0	查询流程	2026-04-19 22:42:02.973549	2026-04-19 22:42:02.97355	f	\N
创建编排节点类型	3	1	module_task:workflow:node-type:create	\N	\N	\N	\N	\N	f	t	f	创建编排节点类型	null	f	147	175	faae2d2b-6638-416d-bf4b-ae35c49061ee	0	创建编排节点类型	2026-04-19 22:42:02.973553	2026-04-19 22:42:02.973554	f	\N
修改编排节点类型	3	2	module_task:workflow:node-type:update	\N	\N	\N	\N	\N	f	t	f	修改编排节点类型	null	f	147	176	b427f074-8138-4149-96e7-2bb73837506d	0	修改编排节点类型	2026-04-19 22:42:02.973557	2026-04-19 22:42:02.973558	f	\N
删除编排节点类型	3	3	module_task:workflow:node-type:delete	\N	\N	\N	\N	\N	f	t	f	删除编排节点类型	null	f	147	177	23a1e0fc-b53a-4b37-82f5-68930e83cf5c	0	删除编排节点类型	2026-04-19 22:42:02.973561	2026-04-19 22:42:02.973561	f	\N
详情编排节点类型	3	4	module_task:workflow:node-type:detail	\N	\N	\N	\N	\N	f	t	f	详情编排节点类型	null	f	147	178	4e8c65a7-cf52-4ba7-8b44-b31dee6ace1c	0	详情编排节点类型	2026-04-19 22:42:02.973565	2026-04-19 22:42:02.973565	f	\N
查询编排节点类型	3	5	module_task:workflow:node-type:query	\N	\N	\N	\N	\N	f	t	f	查询编排节点类型	null	f	147	179	11f70f96-e03b-4085-a441-89570b57a99d	0	查询编排节点类型	2026-04-19 22:42:02.973569	2026-04-19 22:42:02.973569	f	\N
创建示例01	3	1	module_example:demo01:create	\N	\N	\N	\N	\N	f	t	f	创建示例01	null	f	157	180	c57e5132-6773-4984-8da0-6415eddedcbd	0	初始化数据	2026-04-19 22:42:02.973573	2026-04-19 22:42:02.973573	f	\N
更新示例01	3	2	module_example:demo01:update	\N	\N	\N	\N	\N	f	t	f	更新示例01	null	f	157	181	d3392f3b-2dc7-4cb1-93cf-fbc9266ae30e	0	初始化数据	2026-04-19 22:42:02.973577	2026-04-19 22:42:02.973577	f	\N
删除示例01	3	3	module_example:demo01:delete	\N	\N	\N	\N	\N	f	t	f	删除示例01	null	f	157	182	5f572028-0456-4c35-b270-61f544698c00	0	初始化数据	2026-04-19 22:42:02.97358	2026-04-19 22:42:02.973581	f	\N
批量修改示例01状态	3	4	module_example:demo01:patch	\N	\N	\N	\N	\N	f	t	f	批量修改示例01状态	null	f	157	183	1af3ae7b-7515-4b71-8d72-b33af7ecb225	0	初始化数据	2026-04-19 22:42:02.973584	2026-04-19 22:42:02.973585	f	\N
导出示例01	3	5	module_example:demo01:export	\N	\N	\N	\N	\N	f	t	f	导出示例01	null	f	157	184	eb7505fd-230d-4f30-b428-4ec7366cb4a2	0	初始化数据	2026-04-19 22:42:02.973588	2026-04-19 22:42:02.973589	f	\N
导入示例01	3	6	module_example:demo01:import	\N	\N	\N	\N	\N	f	t	f	导入示例01	null	f	157	185	7238f12c-db1a-4cb6-9abc-eb17036bedda	0	初始化数据	2026-04-19 22:42:02.973592	2026-04-19 22:42:02.973592	f	\N
下载导入示例01模版	3	7	module_example:demo01:download	\N	\N	\N	\N	\N	f	t	f	下载导入示例01模版	null	f	157	186	298c00cb-f1a6-4e17-8a1a-f6d5ad0cc266	0	初始化数据	2026-04-19 22:42:02.973596	2026-04-19 22:42:02.973596	f	\N
详情示例01	3	8	module_example:demo01:detail	\N	\N	\N	\N	\N	f	t	f	详情示例01	null	f	157	187	df753484-7763-4925-95c8-ff1ff96a8732	0	初始化数据	2026-04-19 22:42:02.9736	2026-04-19 22:42:02.9736	f	\N
查询示例01	3	9	module_example:demo01:query	\N	\N	\N	\N	\N	f	t	f	查询示例01	null	f	157	188	50e90348-0fe1-4dab-b886-419bcdc4a932	0	初始化数据	2026-04-19 22:42:02.973603	2026-04-19 22:42:02.973604	f	\N
\.


--
-- Data for Name: sys_notice; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_notice (notice_title, notice_type, notice_content, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time, created_id, updated_id, deleted_id) FROM stdin;
\.


--
-- Data for Name: sys_param; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_param (config_name, config_key, config_value, config_type, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time) FROM stdin;
网站名称	sys_web_title	FastApiAdmin	t	1	068a5ac9-f5c0-44fc-80c3-011a6dd4f0b5	0	初始化数据	2026-04-19 22:42:02.979366	2026-04-19 22:42:02.979368	f	\N
网站描述	sys_web_description	FastApiAdmin 是完全开源的权限管理系统	t	2	f4cbc5a9-a678-4443-a2d2-7aac2e9e3f1d	0	初始化数据	2026-04-19 22:42:02.979372	2026-04-19 22:42:02.979373	f	\N
网页图标	sys_web_favicon	https://service.fastapiadmin.com/api/v1/static/image/favicon.png	t	3	16181e3d-87c8-44c5-9fac-d0f3dea0a719	0	初始化数据	2026-04-19 22:42:02.979377	2026-04-19 22:42:02.979377	f	\N
网站Logo	sys_web_logo	https://service.fastapiadmin.com/api/v1/static/image/logo.png	t	4	760e50f2-6130-4152-8f14-bfcd52fe1ee6	0	初始化数据	2026-04-19 22:42:02.979381	2026-04-19 22:42:02.979381	f	\N
登录背景	sys_login_background	https://service.fastapiadmin.com/api/v1/static/image/background.svg	t	5	e701a007-1e6d-462a-87ce-982f34dbfadb	0	初始化数据	2026-04-19 22:42:02.979385	2026-04-19 22:42:02.979386	f	\N
版权信息	sys_web_copyright	Copyright © 2025-2026 service.fastapiadmin.com 版权所有	t	6	2cf41c18-9a98-4e6e-95b9-35107d6d323e	0	初始化数据	2026-04-19 22:42:02.979389	2026-04-19 22:42:02.97939	f	\N
备案信息	sys_keep_record	陕ICP备2025069493号-1	t	7	0c518743-deb9-45b9-999b-954b6915d91a	0	初始化数据	2026-04-19 22:42:02.979393	2026-04-19 22:42:02.979394	f	\N
帮助文档	sys_help_doc	https://service.fastapiadmin.com	t	8	e1281069-d3af-46e6-acaf-9761b4ca055f	0	初始化数据	2026-04-19 22:42:02.979397	2026-04-19 22:42:02.979398	f	\N
隐私政策	sys_web_privacy	https://github.com/fastapiadmin/FastapiAdmin/blob/master/LICENSE	t	9	50d9b606-51ff-4733-bb00-aebd712327e9	0	初始化数据	2026-04-19 22:42:02.979402	2026-04-19 22:42:02.979402	f	\N
用户协议	sys_web_clause	https://github.com/fastapiadmin/FastapiAdmin/blob/master/LICENSE	t	10	7b2c4a81-e77f-456b-a05d-e9faeb10cbe2	0	初始化数据	2026-04-19 22:42:02.979406	2026-04-19 22:42:02.979406	f	\N
源码代码	sys_git_code	https://github.com/fastapiadmin/FastapiAdmin.git	t	11	43687b79-2b1a-4a47-8023-d5c93e3a89cc	0	初始化数据	2026-04-19 22:42:02.979409	2026-04-19 22:42:02.97941	f	\N
项目版本	sys_web_version	2.0.0	t	12	ed8bfab9-9c92-4208-8413-2d28c002134b	0	初始化数据	2026-04-19 22:42:02.979413	2026-04-19 22:42:02.979414	f	\N
演示模式启用	demo_enable	false	t	13	6bb8a61d-d2ac-4171-af59-eeeb0998b48d	0	初始化数据	2026-04-19 22:42:02.979417	2026-04-19 22:42:02.979418	f	\N
演示访问IP白名单	ip_white_list	["127.0.0.1"]	t	14	e8670475-bc38-477c-aeed-dd20ce28dae1	0	初始化数据	2026-04-19 22:42:02.979421	2026-04-19 22:42:02.979422	f	\N
接口白名单	white_api_list_path	["/api/v1/system/auth/login", "/api/v1/system/auth/token/refresh", "/api/v1/system/auth/captcha/get", "/api/v1/system/auth/logout", "/api/v1/system/config/info", "/api/v1/system/user/current/info", "/api/v1/system/notice/available", "/api/v1/system/auth/auto-login/users", "/api/v1/system/auth/auto-login/token", "/api/v1/system/auth/auto-login"]	t	15	15276d15-6c19-40e8-b1af-49242b1ec441	0	初始化数据	2026-04-19 22:42:02.979432	2026-04-19 22:42:02.979433	f	\N
访问IP黑名单	ip_black_list	[]	t	16	d943f2d2-223f-4408-b972-dbb2816a8f0b	0	初始化数据	2026-04-19 22:42:02.979437	2026-04-19 22:42:02.979437	f	\N
\.


--
-- Data for Name: sys_position; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_position (name, "order", id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time, created_id, updated_id, deleted_id) FROM stdin;
\.


--
-- Data for Name: sys_role; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_role (name, code, "order", data_scope, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time) FROM stdin;
管理员角色	ADMIN	1	4	1	115e04a7-32b2-4f52-ae4d-748963c105d7	0	初始化角色	2026-04-19 22:42:02.991365	2026-04-19 22:42:02.991366	f	\N
\.


--
-- Data for Name: sys_role_depts; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_role_depts (role_id, dept_id) FROM stdin;
\.


--
-- Data for Name: sys_role_menus; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_role_menus (role_id, menu_id) FROM stdin;
\.


--
-- Data for Name: sys_tenant; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_tenant (name, code, start_time, end_time, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time) FROM stdin;
系统租户	system	\N	\N	1	227849b3-1637-446f-81e4-0311428e527f	0	平台默认租户，id 固定为 1	2026-04-19 22:42:02.935511	2026-04-19 22:42:02.935521	f	\N
\.


--
-- Data for Name: sys_user; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_user (username, password, name, mobile, email, gender, avatar, is_superuser, last_login, gitee_login, github_login, wx_login, qq_login, dept_id, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time, tenant_id, created_id, updated_id, deleted_id) FROM stdin;
admin	$2b$12$e2IJgS/cvHgJ0H3G7Xa08OXoXnk6N/NX3IZRtubBDElA0VLZhkNOa	超级管理员	\N	\N	0	https://service.fastapiadmin.com/api/v1/static/image/avatar.png	t	\N	\N	\N	\N	\N	1	1	5fcb30eb-be3a-4f21-83a4-7b28bedd720c	0	超级管理员	2026-04-19 22:42:03.010203	2026-04-19 22:42:03.010205	f	\N	1	\N	\N	\N
\.


--
-- Data for Name: sys_user_positions; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_user_positions (user_id, position_id) FROM stdin;
\.


--
-- Data for Name: sys_user_roles; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.sys_user_roles (user_id, role_id) FROM stdin;
1	1
\.


--
-- Data for Name: task_job; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.task_job (job_id, job_name, trigger_type, status, next_run_time, job_state, result, error, id, uuid, description, created_time, updated_time, is_deleted, deleted_time) FROM stdin;
\.


--
-- Data for Name: task_node; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.task_node (name, code, jobstore, executor, trigger, trigger_args, func, args, kwargs, "coalesce", max_instances, start_date, end_date, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time, created_id, updated_id, deleted_id) FROM stdin;
\.


--
-- Data for Name: task_workflow; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.task_workflow (name, code, workflow_status, nodes, edges, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time, created_id, updated_id, deleted_id) FROM stdin;
\.


--
-- Data for Name: task_workflow_node_type; Type: TABLE DATA; Schema: public; Owner: root
--

COPY public.task_workflow_node_type (name, code, category, func, args, kwargs, sort_order, is_active, id, uuid, status, description, created_time, updated_time, is_deleted, deleted_time, created_id, updated_id, deleted_id) FROM stdin;
\.


--
-- Name: app_portal_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.app_portal_id_seq', 1, false);


--
-- Name: gen_demo01_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.gen_demo01_id_seq', 1, false);


--
-- Name: gen_demo_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.gen_demo_id_seq', 1, false);


--
-- Name: gen_table_column_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.gen_table_column_id_seq', 1, false);


--
-- Name: gen_table_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.gen_table_id_seq', 1, false);


--
-- Name: sys_dept_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.sys_dept_id_seq', 1, true);


--
-- Name: sys_dict_data_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.sys_dict_data_id_seq', 34, true);


--
-- Name: sys_dict_type_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.sys_dict_type_id_seq', 10, true);


--
-- Name: sys_log_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.sys_log_id_seq', 1, false);


--
-- Name: sys_menu_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.sys_menu_id_seq', 188, true);


--
-- Name: sys_notice_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.sys_notice_id_seq', 1, false);


--
-- Name: sys_param_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.sys_param_id_seq', 16, true);


--
-- Name: sys_position_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.sys_position_id_seq', 1, false);


--
-- Name: sys_role_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.sys_role_id_seq', 1, true);


--
-- Name: sys_tenant_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.sys_tenant_id_seq', 1, true);


--
-- Name: sys_user_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.sys_user_id_seq', 1, true);


--
-- Name: task_job_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.task_job_id_seq', 1, false);


--
-- Name: task_node_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.task_node_id_seq', 1, false);


--
-- Name: task_workflow_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.task_workflow_id_seq', 1, false);


--
-- Name: task_workflow_node_type_id_seq; Type: SEQUENCE SET; Schema: public; Owner: root
--

SELECT pg_catalog.setval('public.task_workflow_node_type_id_seq', 1, false);


--
-- Name: agno_schema_versions agno_schema_versions_pkey; Type: CONSTRAINT; Schema: ai; Owner: root
--

ALTER TABLE ONLY ai.agno_schema_versions
    ADD CONSTRAINT agno_schema_versions_pkey PRIMARY KEY (table_name);


--
-- Name: agno_sessions agno_sessions_pkey; Type: CONSTRAINT; Schema: ai; Owner: root
--

ALTER TABLE ONLY ai.agno_sessions
    ADD CONSTRAINT agno_sessions_pkey PRIMARY KEY (session_id);


--
-- Name: app_portal app_portal_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.app_portal
    ADD CONSTRAINT app_portal_pkey PRIMARY KEY (id);


--
-- Name: apscheduler_jobs apscheduler_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.apscheduler_jobs
    ADD CONSTRAINT apscheduler_jobs_pkey PRIMARY KEY (id);


--
-- Name: gen_demo01 gen_demo01_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_demo01
    ADD CONSTRAINT gen_demo01_pkey PRIMARY KEY (id);


--
-- Name: gen_demo gen_demo_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_demo
    ADD CONSTRAINT gen_demo_pkey PRIMARY KEY (id);


--
-- Name: gen_table_column gen_table_column_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_table_column
    ADD CONSTRAINT gen_table_column_pkey PRIMARY KEY (id);


--
-- Name: gen_table gen_table_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_table
    ADD CONSTRAINT gen_table_pkey PRIMARY KEY (id);


--
-- Name: sys_dept sys_dept_code_key; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_dept
    ADD CONSTRAINT sys_dept_code_key UNIQUE (code);


--
-- Name: sys_dept sys_dept_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_dept
    ADD CONSTRAINT sys_dept_pkey PRIMARY KEY (id);


--
-- Name: sys_dict_data sys_dict_data_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_dict_data
    ADD CONSTRAINT sys_dict_data_pkey PRIMARY KEY (id);


--
-- Name: sys_dict_type sys_dict_type_dict_type_key; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_dict_type
    ADD CONSTRAINT sys_dict_type_dict_type_key UNIQUE (dict_type);


--
-- Name: sys_dict_type sys_dict_type_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_dict_type
    ADD CONSTRAINT sys_dict_type_pkey PRIMARY KEY (id);


--
-- Name: sys_log sys_log_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_log
    ADD CONSTRAINT sys_log_pkey PRIMARY KEY (id);


--
-- Name: sys_menu sys_menu_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_menu
    ADD CONSTRAINT sys_menu_pkey PRIMARY KEY (id);


--
-- Name: sys_notice sys_notice_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_notice
    ADD CONSTRAINT sys_notice_pkey PRIMARY KEY (id);


--
-- Name: sys_param sys_param_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_param
    ADD CONSTRAINT sys_param_pkey PRIMARY KEY (id);


--
-- Name: sys_position sys_position_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_position
    ADD CONSTRAINT sys_position_pkey PRIMARY KEY (id);


--
-- Name: sys_role sys_role_code_key; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_role
    ADD CONSTRAINT sys_role_code_key UNIQUE (code);


--
-- Name: sys_role_depts sys_role_depts_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_role_depts
    ADD CONSTRAINT sys_role_depts_pkey PRIMARY KEY (role_id, dept_id);


--
-- Name: sys_role_menus sys_role_menus_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_role_menus
    ADD CONSTRAINT sys_role_menus_pkey PRIMARY KEY (role_id, menu_id);


--
-- Name: sys_role sys_role_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_role
    ADD CONSTRAINT sys_role_pkey PRIMARY KEY (id);


--
-- Name: sys_tenant sys_tenant_code_key; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_tenant
    ADD CONSTRAINT sys_tenant_code_key UNIQUE (code);


--
-- Name: sys_tenant sys_tenant_name_key; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_tenant
    ADD CONSTRAINT sys_tenant_name_key UNIQUE (name);


--
-- Name: sys_tenant sys_tenant_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_tenant
    ADD CONSTRAINT sys_tenant_pkey PRIMARY KEY (id);


--
-- Name: sys_user sys_user_email_key; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_email_key UNIQUE (email);


--
-- Name: sys_user sys_user_mobile_key; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_mobile_key UNIQUE (mobile);


--
-- Name: sys_user sys_user_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_pkey PRIMARY KEY (id);


--
-- Name: sys_user_positions sys_user_positions_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user_positions
    ADD CONSTRAINT sys_user_positions_pkey PRIMARY KEY (user_id, position_id);


--
-- Name: sys_user_roles sys_user_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user_roles
    ADD CONSTRAINT sys_user_roles_pkey PRIMARY KEY (user_id, role_id);


--
-- Name: sys_user sys_user_username_key; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_username_key UNIQUE (username);


--
-- Name: task_job task_job_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_job
    ADD CONSTRAINT task_job_pkey PRIMARY KEY (id);


--
-- Name: task_node task_node_code_key; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_node
    ADD CONSTRAINT task_node_code_key UNIQUE (code);


--
-- Name: task_node task_node_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_node
    ADD CONSTRAINT task_node_pkey PRIMARY KEY (id);


--
-- Name: task_workflow_node_type task_workflow_node_type_code_key; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_workflow_node_type
    ADD CONSTRAINT task_workflow_node_type_code_key UNIQUE (code);


--
-- Name: task_workflow_node_type task_workflow_node_type_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_workflow_node_type
    ADD CONSTRAINT task_workflow_node_type_pkey PRIMARY KEY (id);


--
-- Name: task_workflow task_workflow_pkey; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_workflow
    ADD CONSTRAINT task_workflow_pkey PRIMARY KEY (id);


--
-- Name: task_workflow uq_task_workflow_code; Type: CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_workflow
    ADD CONSTRAINT uq_task_workflow_code UNIQUE (code);


--
-- Name: idx_agno_schema_versions_created_at; Type: INDEX; Schema: ai; Owner: root
--

CREATE INDEX idx_agno_schema_versions_created_at ON ai.agno_schema_versions USING btree (created_at);


--
-- Name: idx_agno_sessions_created_at; Type: INDEX; Schema: ai; Owner: root
--

CREATE INDEX idx_agno_sessions_created_at ON ai.agno_sessions USING btree (created_at);


--
-- Name: idx_agno_sessions_session_type; Type: INDEX; Schema: ai; Owner: root
--

CREATE INDEX idx_agno_sessions_session_type ON ai.agno_sessions USING btree (session_type);


--
-- Name: ix_app_portal_created_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_app_portal_created_id ON public.app_portal USING btree (created_id);


--
-- Name: ix_app_portal_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_app_portal_created_time ON public.app_portal USING btree (created_time);


--
-- Name: ix_app_portal_deleted_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_app_portal_deleted_id ON public.app_portal USING btree (deleted_id);


--
-- Name: ix_app_portal_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_app_portal_deleted_time ON public.app_portal USING btree (deleted_time);


--
-- Name: ix_app_portal_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_app_portal_id ON public.app_portal USING btree (id);


--
-- Name: ix_app_portal_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_app_portal_is_deleted ON public.app_portal USING btree (is_deleted);


--
-- Name: ix_app_portal_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_app_portal_status ON public.app_portal USING btree (status);


--
-- Name: ix_app_portal_tenant_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_app_portal_tenant_id ON public.app_portal USING btree (tenant_id);


--
-- Name: ix_app_portal_updated_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_app_portal_updated_id ON public.app_portal USING btree (updated_id);


--
-- Name: ix_app_portal_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_app_portal_updated_time ON public.app_portal USING btree (updated_time);


--
-- Name: ix_app_portal_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_app_portal_uuid ON public.app_portal USING btree (uuid);


--
-- Name: ix_apscheduler_jobs_next_run_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_apscheduler_jobs_next_run_time ON public.apscheduler_jobs USING btree (next_run_time);


--
-- Name: ix_gen_demo01_created_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo01_created_id ON public.gen_demo01 USING btree (created_id);


--
-- Name: ix_gen_demo01_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo01_created_time ON public.gen_demo01 USING btree (created_time);


--
-- Name: ix_gen_demo01_deleted_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo01_deleted_id ON public.gen_demo01 USING btree (deleted_id);


--
-- Name: ix_gen_demo01_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo01_deleted_time ON public.gen_demo01 USING btree (deleted_time);


--
-- Name: ix_gen_demo01_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo01_id ON public.gen_demo01 USING btree (id);


--
-- Name: ix_gen_demo01_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo01_is_deleted ON public.gen_demo01 USING btree (is_deleted);


--
-- Name: ix_gen_demo01_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo01_status ON public.gen_demo01 USING btree (status);


--
-- Name: ix_gen_demo01_updated_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo01_updated_id ON public.gen_demo01 USING btree (updated_id);


--
-- Name: ix_gen_demo01_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo01_updated_time ON public.gen_demo01 USING btree (updated_time);


--
-- Name: ix_gen_demo01_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_gen_demo01_uuid ON public.gen_demo01 USING btree (uuid);


--
-- Name: ix_gen_demo_created_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo_created_id ON public.gen_demo USING btree (created_id);


--
-- Name: ix_gen_demo_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo_created_time ON public.gen_demo USING btree (created_time);


--
-- Name: ix_gen_demo_deleted_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo_deleted_id ON public.gen_demo USING btree (deleted_id);


--
-- Name: ix_gen_demo_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo_deleted_time ON public.gen_demo USING btree (deleted_time);


--
-- Name: ix_gen_demo_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo_id ON public.gen_demo USING btree (id);


--
-- Name: ix_gen_demo_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo_is_deleted ON public.gen_demo USING btree (is_deleted);


--
-- Name: ix_gen_demo_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo_status ON public.gen_demo USING btree (status);


--
-- Name: ix_gen_demo_updated_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo_updated_id ON public.gen_demo USING btree (updated_id);


--
-- Name: ix_gen_demo_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_demo_updated_time ON public.gen_demo USING btree (updated_time);


--
-- Name: ix_gen_demo_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_gen_demo_uuid ON public.gen_demo USING btree (uuid);


--
-- Name: ix_gen_table_column_created_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_column_created_id ON public.gen_table_column USING btree (created_id);


--
-- Name: ix_gen_table_column_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_column_created_time ON public.gen_table_column USING btree (created_time);


--
-- Name: ix_gen_table_column_deleted_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_column_deleted_id ON public.gen_table_column USING btree (deleted_id);


--
-- Name: ix_gen_table_column_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_column_deleted_time ON public.gen_table_column USING btree (deleted_time);


--
-- Name: ix_gen_table_column_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_column_id ON public.gen_table_column USING btree (id);


--
-- Name: ix_gen_table_column_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_column_is_deleted ON public.gen_table_column USING btree (is_deleted);


--
-- Name: ix_gen_table_column_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_column_status ON public.gen_table_column USING btree (status);


--
-- Name: ix_gen_table_column_table_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_column_table_id ON public.gen_table_column USING btree (table_id);


--
-- Name: ix_gen_table_column_updated_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_column_updated_id ON public.gen_table_column USING btree (updated_id);


--
-- Name: ix_gen_table_column_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_column_updated_time ON public.gen_table_column USING btree (updated_time);


--
-- Name: ix_gen_table_column_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_gen_table_column_uuid ON public.gen_table_column USING btree (uuid);


--
-- Name: ix_gen_table_created_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_created_id ON public.gen_table USING btree (created_id);


--
-- Name: ix_gen_table_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_created_time ON public.gen_table USING btree (created_time);


--
-- Name: ix_gen_table_deleted_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_deleted_id ON public.gen_table USING btree (deleted_id);


--
-- Name: ix_gen_table_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_deleted_time ON public.gen_table USING btree (deleted_time);


--
-- Name: ix_gen_table_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_id ON public.gen_table USING btree (id);


--
-- Name: ix_gen_table_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_is_deleted ON public.gen_table USING btree (is_deleted);


--
-- Name: ix_gen_table_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_status ON public.gen_table USING btree (status);


--
-- Name: ix_gen_table_updated_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_updated_id ON public.gen_table USING btree (updated_id);


--
-- Name: ix_gen_table_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_gen_table_updated_time ON public.gen_table USING btree (updated_time);


--
-- Name: ix_gen_table_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_gen_table_uuid ON public.gen_table USING btree (uuid);


--
-- Name: ix_sys_dept_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dept_created_time ON public.sys_dept USING btree (created_time);


--
-- Name: ix_sys_dept_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dept_deleted_time ON public.sys_dept USING btree (deleted_time);


--
-- Name: ix_sys_dept_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dept_id ON public.sys_dept USING btree (id);


--
-- Name: ix_sys_dept_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dept_is_deleted ON public.sys_dept USING btree (is_deleted);


--
-- Name: ix_sys_dept_parent_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dept_parent_id ON public.sys_dept USING btree (parent_id);


--
-- Name: ix_sys_dept_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dept_status ON public.sys_dept USING btree (status);


--
-- Name: ix_sys_dept_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dept_updated_time ON public.sys_dept USING btree (updated_time);


--
-- Name: ix_sys_dept_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_sys_dept_uuid ON public.sys_dept USING btree (uuid);


--
-- Name: ix_sys_dict_data_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dict_data_created_time ON public.sys_dict_data USING btree (created_time);


--
-- Name: ix_sys_dict_data_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dict_data_deleted_time ON public.sys_dict_data USING btree (deleted_time);


--
-- Name: ix_sys_dict_data_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dict_data_id ON public.sys_dict_data USING btree (id);


--
-- Name: ix_sys_dict_data_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dict_data_is_deleted ON public.sys_dict_data USING btree (is_deleted);


--
-- Name: ix_sys_dict_data_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dict_data_status ON public.sys_dict_data USING btree (status);


--
-- Name: ix_sys_dict_data_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dict_data_updated_time ON public.sys_dict_data USING btree (updated_time);


--
-- Name: ix_sys_dict_data_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_sys_dict_data_uuid ON public.sys_dict_data USING btree (uuid);


--
-- Name: ix_sys_dict_type_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dict_type_created_time ON public.sys_dict_type USING btree (created_time);


--
-- Name: ix_sys_dict_type_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dict_type_deleted_time ON public.sys_dict_type USING btree (deleted_time);


--
-- Name: ix_sys_dict_type_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dict_type_id ON public.sys_dict_type USING btree (id);


--
-- Name: ix_sys_dict_type_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dict_type_is_deleted ON public.sys_dict_type USING btree (is_deleted);


--
-- Name: ix_sys_dict_type_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dict_type_status ON public.sys_dict_type USING btree (status);


--
-- Name: ix_sys_dict_type_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_dict_type_updated_time ON public.sys_dict_type USING btree (updated_time);


--
-- Name: ix_sys_dict_type_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_sys_dict_type_uuid ON public.sys_dict_type USING btree (uuid);


--
-- Name: ix_sys_log_created_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_log_created_id ON public.sys_log USING btree (created_id);


--
-- Name: ix_sys_log_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_log_created_time ON public.sys_log USING btree (created_time);


--
-- Name: ix_sys_log_deleted_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_log_deleted_id ON public.sys_log USING btree (deleted_id);


--
-- Name: ix_sys_log_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_log_deleted_time ON public.sys_log USING btree (deleted_time);


--
-- Name: ix_sys_log_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_log_id ON public.sys_log USING btree (id);


--
-- Name: ix_sys_log_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_log_is_deleted ON public.sys_log USING btree (is_deleted);


--
-- Name: ix_sys_log_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_log_status ON public.sys_log USING btree (status);


--
-- Name: ix_sys_log_updated_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_log_updated_id ON public.sys_log USING btree (updated_id);


--
-- Name: ix_sys_log_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_log_updated_time ON public.sys_log USING btree (updated_time);


--
-- Name: ix_sys_log_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_sys_log_uuid ON public.sys_log USING btree (uuid);


--
-- Name: ix_sys_menu_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_menu_created_time ON public.sys_menu USING btree (created_time);


--
-- Name: ix_sys_menu_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_menu_deleted_time ON public.sys_menu USING btree (deleted_time);


--
-- Name: ix_sys_menu_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_menu_id ON public.sys_menu USING btree (id);


--
-- Name: ix_sys_menu_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_menu_is_deleted ON public.sys_menu USING btree (is_deleted);


--
-- Name: ix_sys_menu_parent_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_menu_parent_id ON public.sys_menu USING btree (parent_id);


--
-- Name: ix_sys_menu_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_menu_status ON public.sys_menu USING btree (status);


--
-- Name: ix_sys_menu_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_menu_updated_time ON public.sys_menu USING btree (updated_time);


--
-- Name: ix_sys_menu_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_sys_menu_uuid ON public.sys_menu USING btree (uuid);


--
-- Name: ix_sys_notice_created_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_notice_created_id ON public.sys_notice USING btree (created_id);


--
-- Name: ix_sys_notice_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_notice_created_time ON public.sys_notice USING btree (created_time);


--
-- Name: ix_sys_notice_deleted_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_notice_deleted_id ON public.sys_notice USING btree (deleted_id);


--
-- Name: ix_sys_notice_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_notice_deleted_time ON public.sys_notice USING btree (deleted_time);


--
-- Name: ix_sys_notice_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_notice_id ON public.sys_notice USING btree (id);


--
-- Name: ix_sys_notice_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_notice_is_deleted ON public.sys_notice USING btree (is_deleted);


--
-- Name: ix_sys_notice_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_notice_status ON public.sys_notice USING btree (status);


--
-- Name: ix_sys_notice_updated_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_notice_updated_id ON public.sys_notice USING btree (updated_id);


--
-- Name: ix_sys_notice_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_notice_updated_time ON public.sys_notice USING btree (updated_time);


--
-- Name: ix_sys_notice_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_sys_notice_uuid ON public.sys_notice USING btree (uuid);


--
-- Name: ix_sys_param_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_param_created_time ON public.sys_param USING btree (created_time);


--
-- Name: ix_sys_param_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_param_deleted_time ON public.sys_param USING btree (deleted_time);


--
-- Name: ix_sys_param_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_param_id ON public.sys_param USING btree (id);


--
-- Name: ix_sys_param_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_param_is_deleted ON public.sys_param USING btree (is_deleted);


--
-- Name: ix_sys_param_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_param_status ON public.sys_param USING btree (status);


--
-- Name: ix_sys_param_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_param_updated_time ON public.sys_param USING btree (updated_time);


--
-- Name: ix_sys_param_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_sys_param_uuid ON public.sys_param USING btree (uuid);


--
-- Name: ix_sys_position_created_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_position_created_id ON public.sys_position USING btree (created_id);


--
-- Name: ix_sys_position_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_position_created_time ON public.sys_position USING btree (created_time);


--
-- Name: ix_sys_position_deleted_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_position_deleted_id ON public.sys_position USING btree (deleted_id);


--
-- Name: ix_sys_position_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_position_deleted_time ON public.sys_position USING btree (deleted_time);


--
-- Name: ix_sys_position_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_position_id ON public.sys_position USING btree (id);


--
-- Name: ix_sys_position_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_position_is_deleted ON public.sys_position USING btree (is_deleted);


--
-- Name: ix_sys_position_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_position_status ON public.sys_position USING btree (status);


--
-- Name: ix_sys_position_updated_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_position_updated_id ON public.sys_position USING btree (updated_id);


--
-- Name: ix_sys_position_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_position_updated_time ON public.sys_position USING btree (updated_time);


--
-- Name: ix_sys_position_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_sys_position_uuid ON public.sys_position USING btree (uuid);


--
-- Name: ix_sys_role_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_role_created_time ON public.sys_role USING btree (created_time);


--
-- Name: ix_sys_role_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_role_deleted_time ON public.sys_role USING btree (deleted_time);


--
-- Name: ix_sys_role_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_role_id ON public.sys_role USING btree (id);


--
-- Name: ix_sys_role_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_role_is_deleted ON public.sys_role USING btree (is_deleted);


--
-- Name: ix_sys_role_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_role_status ON public.sys_role USING btree (status);


--
-- Name: ix_sys_role_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_role_updated_time ON public.sys_role USING btree (updated_time);


--
-- Name: ix_sys_role_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_sys_role_uuid ON public.sys_role USING btree (uuid);


--
-- Name: ix_sys_tenant_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_tenant_created_time ON public.sys_tenant USING btree (created_time);


--
-- Name: ix_sys_tenant_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_tenant_deleted_time ON public.sys_tenant USING btree (deleted_time);


--
-- Name: ix_sys_tenant_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_tenant_id ON public.sys_tenant USING btree (id);


--
-- Name: ix_sys_tenant_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_tenant_is_deleted ON public.sys_tenant USING btree (is_deleted);


--
-- Name: ix_sys_tenant_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_tenant_status ON public.sys_tenant USING btree (status);


--
-- Name: ix_sys_tenant_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_tenant_updated_time ON public.sys_tenant USING btree (updated_time);


--
-- Name: ix_sys_tenant_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_sys_tenant_uuid ON public.sys_tenant USING btree (uuid);


--
-- Name: ix_sys_user_created_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_user_created_id ON public.sys_user USING btree (created_id);


--
-- Name: ix_sys_user_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_user_created_time ON public.sys_user USING btree (created_time);


--
-- Name: ix_sys_user_deleted_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_user_deleted_id ON public.sys_user USING btree (deleted_id);


--
-- Name: ix_sys_user_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_user_deleted_time ON public.sys_user USING btree (deleted_time);


--
-- Name: ix_sys_user_dept_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_user_dept_id ON public.sys_user USING btree (dept_id);


--
-- Name: ix_sys_user_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_user_id ON public.sys_user USING btree (id);


--
-- Name: ix_sys_user_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_user_is_deleted ON public.sys_user USING btree (is_deleted);


--
-- Name: ix_sys_user_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_user_status ON public.sys_user USING btree (status);


--
-- Name: ix_sys_user_tenant_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_user_tenant_id ON public.sys_user USING btree (tenant_id);


--
-- Name: ix_sys_user_updated_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_user_updated_id ON public.sys_user USING btree (updated_id);


--
-- Name: ix_sys_user_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_sys_user_updated_time ON public.sys_user USING btree (updated_time);


--
-- Name: ix_sys_user_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_sys_user_uuid ON public.sys_user USING btree (uuid);


--
-- Name: ix_task_job_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_job_created_time ON public.task_job USING btree (created_time);


--
-- Name: ix_task_job_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_job_deleted_time ON public.task_job USING btree (deleted_time);


--
-- Name: ix_task_job_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_job_id ON public.task_job USING btree (id);


--
-- Name: ix_task_job_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_job_is_deleted ON public.task_job USING btree (is_deleted);


--
-- Name: ix_task_job_job_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_job_job_id ON public.task_job USING btree (job_id);


--
-- Name: ix_task_job_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_job_updated_time ON public.task_job USING btree (updated_time);


--
-- Name: ix_task_job_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_task_job_uuid ON public.task_job USING btree (uuid);


--
-- Name: ix_task_node_created_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_node_created_id ON public.task_node USING btree (created_id);


--
-- Name: ix_task_node_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_node_created_time ON public.task_node USING btree (created_time);


--
-- Name: ix_task_node_deleted_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_node_deleted_id ON public.task_node USING btree (deleted_id);


--
-- Name: ix_task_node_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_node_deleted_time ON public.task_node USING btree (deleted_time);


--
-- Name: ix_task_node_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_node_id ON public.task_node USING btree (id);


--
-- Name: ix_task_node_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_node_is_deleted ON public.task_node USING btree (is_deleted);


--
-- Name: ix_task_node_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_node_status ON public.task_node USING btree (status);


--
-- Name: ix_task_node_updated_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_node_updated_id ON public.task_node USING btree (updated_id);


--
-- Name: ix_task_node_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_node_updated_time ON public.task_node USING btree (updated_time);


--
-- Name: ix_task_node_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_task_node_uuid ON public.task_node USING btree (uuid);


--
-- Name: ix_task_workflow_created_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_created_id ON public.task_workflow USING btree (created_id);


--
-- Name: ix_task_workflow_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_created_time ON public.task_workflow USING btree (created_time);


--
-- Name: ix_task_workflow_deleted_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_deleted_id ON public.task_workflow USING btree (deleted_id);


--
-- Name: ix_task_workflow_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_deleted_time ON public.task_workflow USING btree (deleted_time);


--
-- Name: ix_task_workflow_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_id ON public.task_workflow USING btree (id);


--
-- Name: ix_task_workflow_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_is_deleted ON public.task_workflow USING btree (is_deleted);


--
-- Name: ix_task_workflow_node_type_created_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_node_type_created_id ON public.task_workflow_node_type USING btree (created_id);


--
-- Name: ix_task_workflow_node_type_created_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_node_type_created_time ON public.task_workflow_node_type USING btree (created_time);


--
-- Name: ix_task_workflow_node_type_deleted_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_node_type_deleted_id ON public.task_workflow_node_type USING btree (deleted_id);


--
-- Name: ix_task_workflow_node_type_deleted_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_node_type_deleted_time ON public.task_workflow_node_type USING btree (deleted_time);


--
-- Name: ix_task_workflow_node_type_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_node_type_id ON public.task_workflow_node_type USING btree (id);


--
-- Name: ix_task_workflow_node_type_is_deleted; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_node_type_is_deleted ON public.task_workflow_node_type USING btree (is_deleted);


--
-- Name: ix_task_workflow_node_type_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_node_type_status ON public.task_workflow_node_type USING btree (status);


--
-- Name: ix_task_workflow_node_type_updated_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_node_type_updated_id ON public.task_workflow_node_type USING btree (updated_id);


--
-- Name: ix_task_workflow_node_type_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_node_type_updated_time ON public.task_workflow_node_type USING btree (updated_time);


--
-- Name: ix_task_workflow_node_type_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_task_workflow_node_type_uuid ON public.task_workflow_node_type USING btree (uuid);


--
-- Name: ix_task_workflow_status; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_status ON public.task_workflow USING btree (status);


--
-- Name: ix_task_workflow_updated_id; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_updated_id ON public.task_workflow USING btree (updated_id);


--
-- Name: ix_task_workflow_updated_time; Type: INDEX; Schema: public; Owner: root
--

CREATE INDEX ix_task_workflow_updated_time ON public.task_workflow USING btree (updated_time);


--
-- Name: ix_task_workflow_uuid; Type: INDEX; Schema: public; Owner: root
--

CREATE UNIQUE INDEX ix_task_workflow_uuid ON public.task_workflow USING btree (uuid);


--
-- Name: app_portal app_portal_created_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.app_portal
    ADD CONSTRAINT app_portal_created_id_fkey FOREIGN KEY (created_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: app_portal app_portal_deleted_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.app_portal
    ADD CONSTRAINT app_portal_deleted_id_fkey FOREIGN KEY (deleted_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: app_portal app_portal_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.app_portal
    ADD CONSTRAINT app_portal_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.sys_tenant(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: app_portal app_portal_updated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.app_portal
    ADD CONSTRAINT app_portal_updated_id_fkey FOREIGN KEY (updated_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: gen_demo01 gen_demo01_created_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_demo01
    ADD CONSTRAINT gen_demo01_created_id_fkey FOREIGN KEY (created_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: gen_demo01 gen_demo01_deleted_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_demo01
    ADD CONSTRAINT gen_demo01_deleted_id_fkey FOREIGN KEY (deleted_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: gen_demo01 gen_demo01_updated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_demo01
    ADD CONSTRAINT gen_demo01_updated_id_fkey FOREIGN KEY (updated_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: gen_demo gen_demo_created_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_demo
    ADD CONSTRAINT gen_demo_created_id_fkey FOREIGN KEY (created_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: gen_demo gen_demo_deleted_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_demo
    ADD CONSTRAINT gen_demo_deleted_id_fkey FOREIGN KEY (deleted_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: gen_demo gen_demo_updated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_demo
    ADD CONSTRAINT gen_demo_updated_id_fkey FOREIGN KEY (updated_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: gen_table_column gen_table_column_created_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_table_column
    ADD CONSTRAINT gen_table_column_created_id_fkey FOREIGN KEY (created_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: gen_table_column gen_table_column_deleted_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_table_column
    ADD CONSTRAINT gen_table_column_deleted_id_fkey FOREIGN KEY (deleted_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: gen_table_column gen_table_column_table_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_table_column
    ADD CONSTRAINT gen_table_column_table_id_fkey FOREIGN KEY (table_id) REFERENCES public.gen_table(id) ON DELETE CASCADE;


--
-- Name: gen_table_column gen_table_column_updated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_table_column
    ADD CONSTRAINT gen_table_column_updated_id_fkey FOREIGN KEY (updated_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: gen_table gen_table_created_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_table
    ADD CONSTRAINT gen_table_created_id_fkey FOREIGN KEY (created_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: gen_table gen_table_deleted_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_table
    ADD CONSTRAINT gen_table_deleted_id_fkey FOREIGN KEY (deleted_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: gen_table gen_table_updated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.gen_table
    ADD CONSTRAINT gen_table_updated_id_fkey FOREIGN KEY (updated_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_dept sys_dept_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_dept
    ADD CONSTRAINT sys_dept_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.sys_dept(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_dict_data sys_dict_data_dict_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_dict_data
    ADD CONSTRAINT sys_dict_data_dict_type_id_fkey FOREIGN KEY (dict_type_id) REFERENCES public.sys_dict_type(id) ON DELETE CASCADE;


--
-- Name: sys_log sys_log_created_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_log
    ADD CONSTRAINT sys_log_created_id_fkey FOREIGN KEY (created_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_log sys_log_deleted_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_log
    ADD CONSTRAINT sys_log_deleted_id_fkey FOREIGN KEY (deleted_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_log sys_log_updated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_log
    ADD CONSTRAINT sys_log_updated_id_fkey FOREIGN KEY (updated_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_menu sys_menu_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_menu
    ADD CONSTRAINT sys_menu_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.sys_menu(id) ON DELETE SET NULL;


--
-- Name: sys_notice sys_notice_created_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_notice
    ADD CONSTRAINT sys_notice_created_id_fkey FOREIGN KEY (created_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_notice sys_notice_deleted_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_notice
    ADD CONSTRAINT sys_notice_deleted_id_fkey FOREIGN KEY (deleted_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_notice sys_notice_updated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_notice
    ADD CONSTRAINT sys_notice_updated_id_fkey FOREIGN KEY (updated_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_position sys_position_created_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_position
    ADD CONSTRAINT sys_position_created_id_fkey FOREIGN KEY (created_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_position sys_position_deleted_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_position
    ADD CONSTRAINT sys_position_deleted_id_fkey FOREIGN KEY (deleted_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_position sys_position_updated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_position
    ADD CONSTRAINT sys_position_updated_id_fkey FOREIGN KEY (updated_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_role_depts sys_role_depts_dept_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_role_depts
    ADD CONSTRAINT sys_role_depts_dept_id_fkey FOREIGN KEY (dept_id) REFERENCES public.sys_dept(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: sys_role_depts sys_role_depts_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_role_depts
    ADD CONSTRAINT sys_role_depts_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.sys_role(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: sys_role_menus sys_role_menus_menu_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_role_menus
    ADD CONSTRAINT sys_role_menus_menu_id_fkey FOREIGN KEY (menu_id) REFERENCES public.sys_menu(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: sys_role_menus sys_role_menus_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_role_menus
    ADD CONSTRAINT sys_role_menus_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.sys_role(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: sys_user sys_user_created_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_created_id_fkey FOREIGN KEY (created_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_user sys_user_deleted_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_deleted_id_fkey FOREIGN KEY (deleted_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_user sys_user_dept_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_dept_id_fkey FOREIGN KEY (dept_id) REFERENCES public.sys_dept(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sys_user_positions sys_user_positions_position_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user_positions
    ADD CONSTRAINT sys_user_positions_position_id_fkey FOREIGN KEY (position_id) REFERENCES public.sys_position(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: sys_user_positions sys_user_positions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user_positions
    ADD CONSTRAINT sys_user_positions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: sys_user_roles sys_user_roles_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user_roles
    ADD CONSTRAINT sys_user_roles_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.sys_role(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: sys_user_roles sys_user_roles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user_roles
    ADD CONSTRAINT sys_user_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: sys_user sys_user_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.sys_tenant(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: sys_user sys_user_updated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_updated_id_fkey FOREIGN KEY (updated_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: task_node task_node_created_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_node
    ADD CONSTRAINT task_node_created_id_fkey FOREIGN KEY (created_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: task_node task_node_deleted_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_node
    ADD CONSTRAINT task_node_deleted_id_fkey FOREIGN KEY (deleted_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: task_node task_node_updated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_node
    ADD CONSTRAINT task_node_updated_id_fkey FOREIGN KEY (updated_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: task_workflow task_workflow_created_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_workflow
    ADD CONSTRAINT task_workflow_created_id_fkey FOREIGN KEY (created_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: task_workflow task_workflow_deleted_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_workflow
    ADD CONSTRAINT task_workflow_deleted_id_fkey FOREIGN KEY (deleted_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: task_workflow_node_type task_workflow_node_type_created_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_workflow_node_type
    ADD CONSTRAINT task_workflow_node_type_created_id_fkey FOREIGN KEY (created_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: task_workflow_node_type task_workflow_node_type_deleted_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_workflow_node_type
    ADD CONSTRAINT task_workflow_node_type_deleted_id_fkey FOREIGN KEY (deleted_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: task_workflow_node_type task_workflow_node_type_updated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_workflow_node_type
    ADD CONSTRAINT task_workflow_node_type_updated_id_fkey FOREIGN KEY (updated_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: task_workflow task_workflow_updated_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: root
--

ALTER TABLE ONLY public.task_workflow
    ADD CONSTRAINT task_workflow_updated_id_fkey FOREIGN KEY (updated_id) REFERENCES public.sys_user(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict U84VGCVMrsljQl8C3zlCI31HzTnzJhIQqXq4FvOU82CzFlE476WyEoS3uEhMqE8

