// SECURITY: same per-element rule as list_visible_relationships — the edge AND
// both of its endpoints must be visible to the caller (visibility = 'public' OR
// owner_id = $owner_id). Bounded to a pre-selected set of entity ids ($ids) so
// the agent survey needn't read the whole visible graph.
MATCH (a:Entity)-[r:RELATED_TO]->(b:Entity)
WHERE a.id IN $ids AND b.id IN $ids
  AND (a.visibility = 'public' OR a.owner_id = $owner_id)
  AND (b.visibility = 'public' OR b.owner_id = $owner_id)
  AND (r.visibility = 'public' OR r.owner_id = $owner_id)
RETURN r, a.id AS from_id, b.id AS to_id
ORDER BY r.created_at
