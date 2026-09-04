-- Durable record of every agent research run. user_id is the tenant key every
-- read is scoped by; the taskiq worker (backend/app/agent/) updates
-- status/current_node/plan/result and the committed_* arrays as the LangGraph
-- run progresses. The batch commit into Neo4j is not atomic, so the committed_*
-- arrays are the record of partial progress on a failed run.
CREATE TABLE agent_runs (
    id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                    UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    topic                      TEXT NOT NULL,
    status                     TEXT NOT NULL DEFAULT 'queued'
                               CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    current_node               TEXT,
    plan                       JSONB,
    result                     JSONB,
    committed_entity_ids       UUID[] NOT NULL DEFAULT '{}',
    committed_relationship_ids UUID[] NOT NULL DEFAULT '{}',
    error                      TEXT,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The list endpoint returns a user's runs newest-first.
CREATE INDEX agent_runs_user_id_created_at_idx ON agent_runs (user_id, created_at DESC);
