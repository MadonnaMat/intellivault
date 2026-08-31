-- Initial schema: application users. Postgres holds user + auth/credential
-- metadata; the knowledge graph itself lives in Neo4j.
CREATE TABLE users (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email      TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
