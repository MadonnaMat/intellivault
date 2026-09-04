-- Reviewer rejected the drafts — nothing is written to the graph.
UPDATE agent_runs
   SET status = 'cancelled', pending = NULL, updated_at = now()
 WHERE id = $1
RETURNING id, topic, status, current_node, plan, result, pending,
          committed_entity_ids, committed_relationship_ids, error,
          created_at, updated_at;
