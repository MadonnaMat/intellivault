// The "private -> public sub-graph merge" (also runs in reverse). Starting from
// the caller's entity, walk RELATED_TO in either direction and flip every
// reachable entity to $visibility.
//
// SECURITY: every node and every edge on the path is required to be
// owner_id = $owner_id, so the traversal can never leave the caller-owned
// sub-graph and a caller can never flip another user's data.
//
// The *1..25 bound is a deliberate learning-scope guard: an unbounded
// variable-length match on a large graph can walk the whole database. A
// production version would BFS an explicit visited set (or apoc.path.subgraphNodes).
MATCH (start:Entity {id: $id, owner_id: $owner_id})
OPTIONAL MATCH path = (start)-[:RELATED_TO*1..25]-(reached:Entity)
WHERE all(n IN nodes(path) WHERE n.owner_id = $owner_id)
  AND all(rel IN relationships(path) WHERE rel.owner_id = $owner_id)
WITH start, collect(DISTINCT reached) AS reached
WITH [start] + reached AS members
UNWIND members AS m
SET m.visibility = $visibility, m.updated_at = datetime()
RETURN collect(DISTINCT m.id) AS affected_ids
