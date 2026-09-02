// SECURITY: both endpoints must already be visible to the caller (their own or
// public). If either MATCH/WHERE finds nothing the query returns no row and the
// service raises 404 — the caller can't tell "doesn't exist" from "not yours".
// The relationship type must be a Cypher literal (RELATED_TO); the semantic
// label rides in the `kind` property because Community edition has no APOC for
// dynamic types. The edge carries its own owner_id / visibility.
MATCH (a:Entity {id: $from_id})
WHERE a.visibility = 'public' OR a.owner_id = $owner_id
MATCH (b:Entity {id: $to_id})
WHERE b.visibility = 'public' OR b.owner_id = $owner_id
CREATE (a)-[r:RELATED_TO {
  id: $id,
  owner_id: $owner_id,
  visibility: $visibility,
  kind: $kind,
  created_at: datetime(),
  updated_at: datetime()
}]->(b)
RETURN r, a.id AS from_id, b.id AS to_id
