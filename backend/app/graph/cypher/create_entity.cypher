// Create one Entity owned by the caller. `attributes` arrives as a JSON string
// because Neo4j properties can't hold nested maps.
CREATE (e:Entity {
  id: $id,
  owner_id: $owner_id,
  visibility: $visibility,
  name: $name,
  kind: $kind,
  attributes: $attributes,
  created_at: datetime(),
  updated_at: datetime()
})
RETURN e
