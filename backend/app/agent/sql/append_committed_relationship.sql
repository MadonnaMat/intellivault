-- As append_committed_entity, for a RELATED_TO edge.
UPDATE agent_runs
   SET committed_relationship_ids = array_append(committed_relationship_ids, $2),
       updated_at = now()
 WHERE id = $1;
