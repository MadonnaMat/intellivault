-- Human review before commit: a run can pause at `awaiting_review` with its
-- drafted entities in `pending`, then be approved (-> running -> succeeded) or
-- rejected (-> cancelled) via POST /agent/runs/{id}/review.
ALTER TABLE agent_runs DROP CONSTRAINT agent_runs_status_check;
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_status_check
    CHECK (status IN ('queued', 'running', 'awaiting_review', 'succeeded', 'failed', 'cancelled'));

ALTER TABLE agent_runs ADD COLUMN pending JSONB;
