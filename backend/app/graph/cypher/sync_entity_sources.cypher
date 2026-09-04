// SECURITY: $ids are already this caller's own entities (verified by
// set_entity_visibility / flip_entities earlier in the same transaction), but
// owner_id is still bound here per the blanket rule every :Entity-touching
// query follows.
//
// Mirrors each flipped entity's new visibility onto its SOURCED_FROM edges.
// Source nodes themselves are always public (see attach_sources.cypher), so
// there's nothing on the Source side to recompute.
MATCH (e:Entity)-[r:SOURCED_FROM]->(s:Source)
WHERE e.id IN $ids AND e.owner_id = $owner_id
SET r.visibility = e.visibility
