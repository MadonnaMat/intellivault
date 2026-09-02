// SECURITY: the edge AND both of its endpoints must be visible to the caller.
// A private edge between two public nodes stays hidden from everyone but its
// owner — visibility is per-element, not inherited.
MATCH (a:Entity)-[r:RELATED_TO]->(b:Entity)
WHERE (a.visibility = 'public' OR a.owner_id = $owner_id)
  AND (b.visibility = 'public' OR b.owner_id = $owner_id)
  AND (r.visibility = 'public' OR r.owner_id = $owner_id)
RETURN r, a.id AS from_id, b.id AS to_id
ORDER BY r.created_at
