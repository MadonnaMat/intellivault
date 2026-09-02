// SECURITY: the cascade only starts if the caller owns the starting entity;
// an empty result means the service raises 404.
MATCH (e:Entity {id: $id, owner_id: $owner_id})
RETURN e.id AS id
