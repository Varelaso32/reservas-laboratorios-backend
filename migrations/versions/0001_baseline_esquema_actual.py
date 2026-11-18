"""Esquema base del proyecto (estado previo a las migraciones versionadas).

Reproduce exactamente el esquema que existía antes de introducir Alembic:
tablas, restricciones (incluida la de exclusión que impide reservas cruzadas),
índices, secuencias y el trigger que hace la trazabilidad de solo inserción.

En las bases que ya existían se marca como aplicada sin ejecutarla:
    alembic stamp 0001_baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# DDL del esquema base, en el mismo orden en que lo crea la aplicación.
STATEMENTS: tuple[str, ...] = (
    'CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;',
    "COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';",
    "CREATE FUNCTION public.trazabilidad_bloquear_cambios() RETURNS trigger\n\n    LANGUAGE plpgsql\n\n    AS $$\n\nBEGIN\n\n    RAISE EXCEPTION 'La trazabilidad no se puede modificar ni eliminar';\n\nEND;\n\n$$;",
    "CREATE TABLE public.espacio (\n\n    id integer NOT NULL,\n\n    nombre character varying(120) NOT NULL,\n\n    tipo character varying(30) NOT NULL,\n\n    capacidad integer NOT NULL,\n\n    ubicacion character varying(200),\n\n    activo boolean DEFAULT true NOT NULL,\n\n    creado_en timestamp with time zone DEFAULT now() NOT NULL,\n\n    CONSTRAINT ck_espacio_capacidad_positiva CHECK ((capacidad > 0)),\n\n    CONSTRAINT ck_espacio_tipo_espacio CHECK (((tipo)::text = ANY ((ARRAY['LABORATORIO'::character varying, 'SALA'::character varying])::text[])))\n\n);",
    'CREATE TABLE public.espacio_aprobador (\n\n    espacio_id integer NOT NULL,\n\n    usuario_id integer NOT NULL\n\n);',
    'CREATE SEQUENCE public.espacio_id_seq\n\n    AS integer\n\n    START WITH 1\n\n    INCREMENT BY 1\n\n    NO MINVALUE\n\n    NO MAXVALUE\n\n    CACHE 1;',
    'ALTER SEQUENCE public.espacio_id_seq OWNED BY public.espacio.id;',
    "CREATE TABLE public.reserva (\n\n    id integer NOT NULL,\n\n    solicitud_id integer NOT NULL,\n\n    espacio_id integer NOT NULL,\n\n    usuario_id integer NOT NULL,\n\n    inicio timestamp with time zone NOT NULL,\n\n    fin timestamp with time zone NOT NULL,\n\n    estado character varying(30) DEFAULT 'ACTIVA'::character varying NOT NULL,\n\n    creada_en timestamp with time zone DEFAULT now() NOT NULL,\n\n    CONSTRAINT ck_reserva_estado_reserva CHECK (((estado)::text = ANY ((ARRAY['ACTIVA'::character varying, 'CANCELADA'::character varying])::text[]))),\n\n    CONSTRAINT ck_reserva_rango_valido CHECK ((fin > inicio))\n\n);",
    'CREATE SEQUENCE public.reserva_id_seq\n\n    AS integer\n\n    START WITH 1\n\n    INCREMENT BY 1\n\n    NO MINVALUE\n\n    NO MAXVALUE\n\n    CACHE 1;',
    'ALTER SEQUENCE public.reserva_id_seq OWNED BY public.reserva.id;',
    "CREATE TABLE public.solicitud (\n\n    id integer NOT NULL,\n\n    solicitante_id integer NOT NULL,\n\n    espacio_id integer NOT NULL,\n\n    inicio timestamp with time zone NOT NULL,\n\n    fin timestamp with time zone NOT NULL,\n\n    proposito text NOT NULL,\n\n    asistentes integer NOT NULL,\n\n    equipamiento text,\n\n    estado character varying(30) DEFAULT 'PENDIENTE'::character varying NOT NULL,\n\n    decidido_por integer,\n\n    fecha_decision timestamp with time zone,\n\n    motivo_rechazo text,\n\n    creada_en timestamp with time zone DEFAULT now() NOT NULL,\n\n    CONSTRAINT ck_solicitud_asistentes_positivos CHECK ((asistentes > 0)),\n\n    CONSTRAINT ck_solicitud_decision_con_responsable CHECK ((((estado)::text <> ALL ((ARRAY['APROBADA'::character varying, 'RECHAZADA'::character varying])::text[])) OR ((decidido_por IS NOT NULL) AND (fecha_decision IS NOT NULL)))),\n\n    CONSTRAINT ck_solicitud_estado_solicitud CHECK (((estado)::text = ANY ((ARRAY['PENDIENTE'::character varying, 'APROBADA'::character varying, 'RECHAZADA'::character varying, 'CANCELADA'::character varying])::text[]))),\n\n    CONSTRAINT ck_solicitud_rango_valido CHECK ((fin > inicio)),\n\n    CONSTRAINT ck_solicitud_rechazo_con_motivo CHECK ((((estado)::text <> 'RECHAZADA'::text) OR (length(TRIM(BOTH FROM COALESCE(motivo_rechazo, ''::text))) > 0)))\n\n);",
    'CREATE SEQUENCE public.solicitud_id_seq\n\n    AS integer\n\n    START WITH 1\n\n    INCREMENT BY 1\n\n    NO MINVALUE\n\n    NO MAXVALUE\n\n    CACHE 1;',
    'ALTER SEQUENCE public.solicitud_id_seq OWNED BY public.solicitud.id;',
    "CREATE TABLE public.trazabilidad (\n\n    id bigint NOT NULL,\n\n    solicitud_id integer NOT NULL,\n\n    reserva_id integer,\n\n    usuario_id integer NOT NULL,\n\n    accion character varying(30) NOT NULL,\n\n    estado_anterior character varying(30),\n\n    estado_nuevo character varying(30),\n\n    detalle text,\n\n    fecha timestamp with time zone DEFAULT clock_timestamp() NOT NULL,\n\n    CONSTRAINT ck_trazabilidad_accion_trazabilidad CHECK (((accion)::text = ANY ((ARRAY['CREADA'::character varying, 'APROBADA'::character varying, 'RECHAZADA'::character varying, 'CANCELADA'::character varying])::text[])))\n\n);",
    'CREATE SEQUENCE public.trazabilidad_id_seq\n\n    START WITH 1\n\n    INCREMENT BY 1\n\n    NO MINVALUE\n\n    NO MAXVALUE\n\n    CACHE 1;',
    'ALTER SEQUENCE public.trazabilidad_id_seq OWNED BY public.trazabilidad.id;',
    "CREATE TABLE public.usuario (\n\n    id integer NOT NULL,\n\n    nombre character varying(120) NOT NULL,\n\n    email character varying(254) NOT NULL,\n\n    clave_hash character varying(255) NOT NULL,\n\n    rol character varying(30) NOT NULL,\n\n    cargo character varying(30),\n\n    activo boolean DEFAULT true NOT NULL,\n\n    creado_en timestamp with time zone DEFAULT now() NOT NULL,\n\n    CONSTRAINT ck_usuario_cargo CHECK (((cargo)::text = ANY ((ARRAY['ESTUDIANTE'::character varying, 'DOCENTE'::character varying, 'ADMINISTRATIVO'::character varying, 'COORDINADOR_LABORATORIOS'::character varying, 'ADMINISTRADOR_SALA'::character varying, 'ADMINISTRADOR_SISTEMA'::character varying])::text[]))),\n\n    CONSTRAINT ck_usuario_rol CHECK (((rol)::text = ANY ((ARRAY['SOLICITANTE'::character varying, 'APROBADOR'::character varying, 'ADMIN'::character varying])::text[])))\n\n);",
    'CREATE SEQUENCE public.usuario_id_seq\n\n    AS integer\n\n    START WITH 1\n\n    INCREMENT BY 1\n\n    NO MINVALUE\n\n    NO MAXVALUE\n\n    CACHE 1;',
    'ALTER SEQUENCE public.usuario_id_seq OWNED BY public.usuario.id;',
    "ALTER TABLE ONLY public.espacio ALTER COLUMN id SET DEFAULT nextval('public.espacio_id_seq'::regclass);",
    "ALTER TABLE ONLY public.reserva ALTER COLUMN id SET DEFAULT nextval('public.reserva_id_seq'::regclass);",
    "ALTER TABLE ONLY public.solicitud ALTER COLUMN id SET DEFAULT nextval('public.solicitud_id_seq'::regclass);",
    "ALTER TABLE ONLY public.trazabilidad ALTER COLUMN id SET DEFAULT nextval('public.trazabilidad_id_seq'::regclass);",
    "ALTER TABLE ONLY public.usuario ALTER COLUMN id SET DEFAULT nextval('public.usuario_id_seq'::regclass);",
    "ALTER TABLE ONLY public.reserva\n\n    ADD CONSTRAINT ex_reserva_sin_cruce EXCLUDE USING gist (espacio_id WITH =, tstzrange(inicio, fin, '[)'::text) WITH &&) WHERE (((estado)::text = 'ACTIVA'::text));",
    'ALTER TABLE ONLY public.espacio\n\n    ADD CONSTRAINT pk_espacio PRIMARY KEY (id);',
    'ALTER TABLE ONLY public.espacio_aprobador\n\n    ADD CONSTRAINT pk_espacio_aprobador PRIMARY KEY (espacio_id, usuario_id);',
    'ALTER TABLE ONLY public.reserva\n\n    ADD CONSTRAINT pk_reserva PRIMARY KEY (id);',
    'ALTER TABLE ONLY public.solicitud\n\n    ADD CONSTRAINT pk_solicitud PRIMARY KEY (id);',
    'ALTER TABLE ONLY public.trazabilidad\n\n    ADD CONSTRAINT pk_trazabilidad PRIMARY KEY (id);',
    'ALTER TABLE ONLY public.usuario\n\n    ADD CONSTRAINT pk_usuario PRIMARY KEY (id);',
    'ALTER TABLE ONLY public.espacio\n\n    ADD CONSTRAINT uq_espacio_nombre UNIQUE (nombre);',
    'ALTER TABLE ONLY public.reserva\n\n    ADD CONSTRAINT uq_reserva_solicitud_id UNIQUE (solicitud_id);',
    'CREATE INDEX ix_reserva_usuario_estado ON public.reserva USING btree (usuario_id, estado);',
    'CREATE INDEX ix_solicitud_espacio_estado ON public.solicitud USING btree (espacio_id, estado);',
    'CREATE INDEX ix_solicitud_solicitante ON public.solicitud USING btree (solicitante_id);',
    'CREATE INDEX ix_trazabilidad_solicitud_orden ON public.trazabilidad USING btree (solicitud_id, fecha, id);',
    'CREATE UNIQUE INDEX ux_usuario_email_lower ON public.usuario USING btree (lower((email)::text));',
    'CREATE TRIGGER trazabilidad_solo_insercion BEFORE DELETE OR UPDATE ON public.trazabilidad FOR EACH ROW EXECUTE FUNCTION public.trazabilidad_bloquear_cambios();',
    'ALTER TABLE ONLY public.espacio_aprobador\n\n    ADD CONSTRAINT fk_espacio_aprobador_espacio_id_espacio FOREIGN KEY (espacio_id) REFERENCES public.espacio(id) ON DELETE CASCADE;',
    'ALTER TABLE ONLY public.espacio_aprobador\n\n    ADD CONSTRAINT fk_espacio_aprobador_usuario_id_usuario FOREIGN KEY (usuario_id) REFERENCES public.usuario(id) ON DELETE CASCADE;',
    'ALTER TABLE ONLY public.reserva\n\n    ADD CONSTRAINT fk_reserva_espacio_id_espacio FOREIGN KEY (espacio_id) REFERENCES public.espacio(id);',
    'ALTER TABLE ONLY public.reserva\n\n    ADD CONSTRAINT fk_reserva_solicitud_id_solicitud FOREIGN KEY (solicitud_id) REFERENCES public.solicitud(id);',
    'ALTER TABLE ONLY public.reserva\n\n    ADD CONSTRAINT fk_reserva_usuario_id_usuario FOREIGN KEY (usuario_id) REFERENCES public.usuario(id);',
    'ALTER TABLE ONLY public.solicitud\n\n    ADD CONSTRAINT fk_solicitud_decidido_por_usuario FOREIGN KEY (decidido_por) REFERENCES public.usuario(id);',
    'ALTER TABLE ONLY public.solicitud\n\n    ADD CONSTRAINT fk_solicitud_espacio_id_espacio FOREIGN KEY (espacio_id) REFERENCES public.espacio(id);',
    'ALTER TABLE ONLY public.solicitud\n\n    ADD CONSTRAINT fk_solicitud_solicitante_id_usuario FOREIGN KEY (solicitante_id) REFERENCES public.usuario(id);',
    'ALTER TABLE ONLY public.trazabilidad\n\n    ADD CONSTRAINT fk_trazabilidad_reserva_id_reserva FOREIGN KEY (reserva_id) REFERENCES public.reserva(id);',
    'ALTER TABLE ONLY public.trazabilidad\n\n    ADD CONSTRAINT fk_trazabilidad_solicitud_id_solicitud FOREIGN KEY (solicitud_id) REFERENCES public.solicitud(id);',
    'ALTER TABLE ONLY public.trazabilidad\n\n    ADD CONSTRAINT fk_trazabilidad_usuario_id_usuario FOREIGN KEY (usuario_id) REFERENCES public.usuario(id);',
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trazabilidad_solo_insercion ON trazabilidad")
    for table in (
        "trazabilidad",
        "reserva",
        "solicitud",
        "espacio_aprobador",
        "espacio",
        "usuario",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS trazabilidad_bloquear_cambios()")
