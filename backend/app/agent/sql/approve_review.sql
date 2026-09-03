-- Reviewer approved (optionally with edits in $2). Back to running; a resume
-- job commits the pending drafts.
UPDATE agent_runs
   SET status = 'running', pending = $2::jsonb, error = NULL, updated_at = now()
 WHERE id = $1
RETURNING id, topic, status, current_node, plan, result, pending,
          committed_entity_ids, committed_relationship_ids, error,
          created_at, updated_at;
