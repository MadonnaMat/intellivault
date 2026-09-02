// SECURITY: owner_id is in the node pattern, so only the caller's own entity
// matches. A non-match returns no row and the service raises 404 — never 403.
MATCH (e:Entity {id: $id, owner_id: $owner_id})
SET e.visibility = $visibility, e.updated_at = datetime()
RETURN e.id AS id
