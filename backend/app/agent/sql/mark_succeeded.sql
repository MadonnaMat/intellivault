-- The run finished. $3/$4 are the authoritative committed-id lists (the
-- incremental array_appends should already match, but a failed append won't
-- have — the final write wins).
UPDATE agent_runs
   SET status = 'succeeded',
       current_node = NULL,
       result = $2::jsonb,
       committed_entity_ids = $3,
       committed_relationship_ids = $4,
       updated_at = now()
 WHERE id = $1;
