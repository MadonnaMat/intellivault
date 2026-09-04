// Reverse of 0003. IF EXISTS makes a missing constraint a no-op. Existing
// :Source nodes and SOURCED_FROM edges are left in place — dropping the
// constraint doesn't require deleting data.
DROP CONSTRAINT source_url_unique IF EXISTS;
