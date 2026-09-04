-- Create a queued run. The worker fills in everything else.
INSERT INTO agent_runs (user_id, topic)
VALUES ($1, $2)
RETURNING id, topic, status, current_node, plan, result, pending,
          committed_entity_ids, committed_relationship_ids, error,
          created_at, updated_at;
