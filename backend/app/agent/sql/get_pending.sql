-- The drafts an approved run should commit, plus the research phase's partial
-- result (analysis + skipped notes) parked alongside them.
SELECT pending, result FROM agent_runs WHERE id = $1;
