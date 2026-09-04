-- One run, scoped to its owner. A missing OR foreign row returns nothing (the
-- route turns that into a 404 — never a 403, don't leak existence).
SELECT id, topic, status, current_node, plan, result, pending,
       committed_entity_ids, committed_relationship_ids, error,
       created_at, updated_at
  FROM agent_runs
 WHERE id = $1 AND user_id = $2;
