// SECURITY: owner_id is in the node pattern, so only the caller's own entity
// matches. A non-match returns no row and the service raises 404 — never 403.
// DETACH also removes every relationship on the entity (including ones another
// user attached to it).
MATCH (e:Entity {id: $id, owner_id: $owner_id})
WITH e, e.id AS id
DETACH DELETE e
RETURN id
