// When entities in $ids go private: any relationship the caller does NOT own
// that is incident to one of them is removed — its owner can no longer see the
// node it points at, so the edge just dangles.
//
// SECURITY: only edges with r.owner_id <> $owner_id are deleted; the caller's
// own edges are handled by demote_owned_edges.
MATCH (e:Entity)-[r:RELATED_TO]-(:Entity)
WHERE e.id IN $ids AND r.owner_id <> $owner_id
DELETE r
RETURN count(r) AS removed
