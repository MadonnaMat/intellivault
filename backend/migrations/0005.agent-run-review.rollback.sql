ALTER TABLE agent_runs DROP COLUMN pending;
ALTER TABLE agent_runs DROP CONSTRAINT agent_runs_status_check;
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_status_check
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed'));
