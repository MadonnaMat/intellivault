// When entities in $ids go private: any public relationship the caller owns that
// is incident to one of them becomes private too (an edge can't be more visible
// than its endpoints).
//
// SECURITY: only r.owner_id = $owner_id edges are touched.
MATCH (e:Entity)-[r:RELATED_TO]-(:Entity)
WHERE e.id IN $ids AND r.owner_id = $owner_id AND r.visibility = 'public'
SET r.visibility = 'private', r.updated_at = datetime()
RETURN count(r) AS changed
