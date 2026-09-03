-- A user's runs, newest first (backed by agent_runs_user_id_created_at_idx).
SELECT id, topic, status, created_at, updated_at
  FROM agent_runs
 WHERE user_id = $1
 ORDER BY created_at DESC;
