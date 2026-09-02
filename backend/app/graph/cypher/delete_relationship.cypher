// SECURITY: you may remove an edge you own, OR any edge attached to an entity
// you own — so if another user links something to your node you can detach it.
// A non-match returns no row and the service raises 404.
MATCH (a:Entity)-[r:RELATED_TO {id: $id}]-(b:Entity)
WHERE r.owner_id = $owner_id OR a.owner_id = $owner_id OR b.owner_id = $owner_id
WITH r, r.id AS id
DELETE r
RETURN id
