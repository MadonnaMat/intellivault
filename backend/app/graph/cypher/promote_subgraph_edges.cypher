// Second half of the cascade: flip every caller-owned relationship that runs
// between two entities already promoted by promote_subgraph_nodes.
//
// SECURITY: r.owner_id = $owner_id, and both endpoints must be in $ids (the set
// promote_subgraph_nodes just returned), so only edges wholly inside the
// caller-owned sub-graph are touched.
MATCH (a:Entity)-[r:RELATED_TO]-(b:Entity)
WHERE a.id IN $ids AND b.id IN $ids AND r.owner_id = $owner_id
SET r.visibility = $visibility, r.updated_at = datetime()
RETURN count(r) AS updated
