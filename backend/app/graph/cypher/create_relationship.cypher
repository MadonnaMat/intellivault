// SECURITY: both endpoints must be visible to the caller (own or public), AND
// the caller must own at least one of them — so you can link your own entity to
// a public one, but you cannot fabricate an edge between two public entities you
// don't own. If nothing matches, the query returns no row and the service
// raises 404 (the caller can't tell "missing" from "not yours").
// The relationship type must be a Cypher literal (RELATED_TO); the semantic
// label rides in the `kind` property because Community edition has no APOC for
// dynamic types. The edge carries its own owner_id / visibility.
MATCH (a:Entity {id: $from_id})
WHERE a.visibility = 'public' OR a.owner_id = $owner_id
MATCH (b:Entity {id: $to_id})
WHERE b.visibility = 'public' OR b.owner_id = $owner_id
WITH a, b
WHERE a.owner_id = $owner_id OR b.owner_id = $owner_id
CREATE (a)-[r:RELATED_TO {
  id: $id,
  owner_id: $owner_id,
  visibility: $visibility,
  kind: $kind,
  created_at: datetime(),
  updated_at: datetime()
}]->(b)
RETURN r, a.id AS from_id, b.id AS to_id
