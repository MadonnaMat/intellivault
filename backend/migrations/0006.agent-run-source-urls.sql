-- The URLs a run's research phase fetched, parked alongside `pending` so the
-- commit phase (after human review) can re-attach sources to the entities it
-- creates — see app.graph.service.attach_sources. Worker-internal only, never
-- exposed on any response schema.
ALTER TABLE agent_runs ADD COLUMN source_urls JSONB NOT NULL DEFAULT '[]'::jsonb;
