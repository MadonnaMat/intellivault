// Flip the visibility of every entity in $ids that the caller owns and whose
// visibility actually differs — returns exactly the ids that changed.
//
// SECURITY: owner_id = $owner_id, so a stray id in the set (or a concurrently
// re-owned node) can't be touched.
MATCH (e:Entity)
WHERE e.id IN $ids AND e.owner_id = $owner_id AND e.visibility <> $visibility
SET e.visibility = $visibility, e.updated_at = datetime()
RETURN collect(e.id) AS changed
