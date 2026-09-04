-- The worker has picked the job up. Clear any error from a previous attempt.
UPDATE agent_runs
   SET status = 'running', current_node = NULL, error = NULL, updated_at = now()
 WHERE id = $1;
