// SECURITY: only the owner may (re)embed their own entity. The write is scoped
// by owner_id in the node pattern, so another user's id (or a public entity the
// caller doesn't own) simply matches nothing and the caller gets a 404.
MATCH (e:Entity {id: $id, owner_id: $owner_id})
SET e.embedding = $embedding
RETURN e.id AS id
