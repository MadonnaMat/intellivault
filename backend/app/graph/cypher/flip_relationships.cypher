// Flip every caller-owned relationship that runs between two entities in $ids
// (the set flip_entities just promoted) and whose visibility differs.
//
// SECURITY: r.owner_id = $owner_id and both endpoints in $ids, so only edges
// wholly inside the caller-owned sub-graph are touched.
MATCH (a:Entity)-[r:RELATED_TO]-(b:Entity)
WHERE a.id IN $ids AND b.id IN $ids
  AND r.owner_id = $owner_id AND r.visibility <> $visibility
SET r.visibility = $visibility, r.updated_at = datetime()
RETURN count(r) AS changed
