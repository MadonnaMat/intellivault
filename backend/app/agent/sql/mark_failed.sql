-- The run raised. Keep whatever was committed before the failure so the caller
-- can see (and, later, clean up) the partial result.
UPDATE agent_runs
   SET status = 'failed',
       error = $2,
       committed_entity_ids = $3,
       committed_relationship_ids = $4,
       updated_at = now()
 WHERE id = $1;
