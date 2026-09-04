// SECURITY: db.index.vector.queryNodes has no tenancy of its own — the WHERE
// clause is the entire property-level boundary here, the same predicate every
// entity read uses: the caller sees their own entities plus public ones, and
// never another user's private entity. visibility = 'public' OR owner_id = $owner_id.
CALL db.index.vector.queryNodes('entity_embedding', $k, $embedding)
YIELD node AS e, score
WHERE e:Entity AND (e.visibility = 'public' OR e.owner_id = $owner_id)
RETURN e, score
ORDER BY score DESC
