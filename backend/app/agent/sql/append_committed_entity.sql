-- Record one entity the moment it lands in Neo4j — the batch commit is not
-- atomic, so this array is the accurate record of partial progress on a crash.
UPDATE agent_runs
   SET committed_entity_ids = array_append(committed_entity_ids, $2),
       updated_at = now()
 WHERE id = $1;
