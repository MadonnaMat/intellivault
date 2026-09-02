// SECURITY: both endpoints must be visible to the caller (own or public), AND
// the caller must own at least one of them, AND a public edge is only allowed
// between two public entities — an edge must not be more visible than its
// endpoints. On any violation the query returns no row and the service runs a
// diagnostic to pick 404 (missing / not visible / not owned) vs 422 (a public
// edge with a private endpoint).
// The relationship type must be a Cypher literal (RELATED_TO); the semantic
// label rides in the `kind` property because Community edition has no APOC for
// dynamic types. The edge carries its own owner_id / visibility.
MATCH (a:Entity {id: $from_id})
WHERE a.visibility = 'public' OR a.owner_id = $owner_id
MATCH (b:Entity {id: $to_id})
WHERE b.visibility = 'public' OR b.owner_id = $owner_id
WITH a, b
WHERE (a.owner_id = $owner_id OR b.owner_id = $owner_id)
  AND ($visibility = 'private' OR (a.visibility = 'public' AND b.visibility = 'public'))
CREATE (a)-[r:RELATED_TO {
  id: $id,
  owner_id: $owner_id,
  visibility: $visibility,
  kind: $kind,
  created_at: datetime(),
  updated_at: datetime()
}]->(b)
RETURN r, a.id AS from_id, b.id AS to_id
