// The same visibility / ownership gate as create_relationship, but returning the
// endpoint visibilities instead of creating anything. Used only to explain a
// rejected create (404 vs 422).
//
// SECURITY: an empty result means the endpoints aren't both visible to the
// caller, or the caller owns neither.
MATCH (a:Entity {id: $from_id})
WHERE a.visibility = 'public' OR a.owner_id = $owner_id
MATCH (b:Entity {id: $to_id})
WHERE b.visibility = 'public' OR b.owner_id = $owner_id
WITH a, b
WHERE a.owner_id = $owner_id OR b.owner_id = $owner_id
RETURN a.visibility AS from_visibility, b.visibility AS to_visibility
