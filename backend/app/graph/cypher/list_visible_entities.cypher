// SECURITY: a caller sees their own entities plus every public entity,
// and never another user's private entity. This predicate is the whole of
// property-level security on reads (Neo4j Community has no row/property RBAC).
MATCH (e:Entity)
WHERE e.visibility = 'public' OR e.owner_id = $owner_id
RETURN e
ORDER BY e.created_at
