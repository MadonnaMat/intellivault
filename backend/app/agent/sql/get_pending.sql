-- The drafts an approved run should commit.
SELECT pending FROM agent_runs WHERE id = $1;
