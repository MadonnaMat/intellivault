// SECURITY: a caller sees their own entities plus every public entity,
// and never another user's private entity. This predicate is the whole of
// property-level security on reads (Neo4j Community has no row/property RBAC).
//
// Sources are attached alongside whichever entities already passed the
// predicate above — a caller who can see the entity can see what it cites,
// regardless of the Source's own aggregate visibility (a different, broader
// concern: whether some other user's entity also makes it visible to them).
MATCH (e:Entity)
WHERE e.visibility = 'public' OR e.owner_id = $owner_id
OPTIONAL MATCH (e)-[:SOURCED_FROM]->(s:Source)
WITH e, collect(DISTINCT s.url) AS sources
RETURN e, sources
ORDER BY e.created_at
