// SECURITY: owner_id is in the node pattern, so only the caller's own entity
// matches. A non-match returns no row and the service raises 404 — never 403.
// `changed` is false when the entity is already at the target visibility, so the
// service can report only entities that actually changed.
MATCH (e:Entity {id: $id, owner_id: $owner_id})
WITH e, e.visibility <> $visibility AS changed
FOREACH (_ IN CASE WHEN changed THEN [1] ELSE [] END |
  SET e.visibility = $visibility, e.updated_at = datetime())
RETURN e.id AS id, changed
