// One hop of the caller-owned connected sub-graph: from the entities in $ids,
// every adjacent entity the caller owns, reached via a relationship the caller
// owns. The service calls this repeatedly (BFS) until the set stops growing —
// bounded by the sub-graph itself, not an arbitrary depth limit, and each hop
// is a single indexed lookup rather than a path enumeration.
//
// SECURITY: both the neighbour and the connecting edge must be owner_id =
// $owner_id, so the walk can never leave the caller-owned sub-graph.
MATCH (a:Entity)-[r:RELATED_TO]-(b:Entity)
WHERE a.id IN $ids
  AND b.owner_id = $owner_id
  AND r.owner_id = $owner_id
RETURN DISTINCT b.id AS id
