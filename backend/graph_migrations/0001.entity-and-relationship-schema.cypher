// 0001 — entity + relationship schema
//
// Neo4j is schema-optional: there is no CREATE TABLE, any node may carry any
// label or property. The only things you declare up front are uniqueness
// CONSTRAINTs (which also build a lookup index) and INDEXes to keep
// MATCH ... WHERE fast. Every statement is idempotent (IF NOT EXISTS).

// Every Entity is addressed by its app-generated UUID.
CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
FOR (e:Entity) REQUIRE e.id IS UNIQUE;

// Backs the property-level security predicate every entity read uses:
//   WHERE e.visibility = 'public' OR e.owner_id = $owner_id
CREATE INDEX entity_owner_visibility IF NOT EXISTS
FOR (e:Entity) ON (e.owner_id, e.visibility);

// RELATED_TO edges carry their own app-generated UUID; index it for lookups.
CREATE INDEX related_to_id IF NOT EXISTS
FOR ()-[r:RELATED_TO]-() ON (r.id);

// Backs the security predicate for relationship reads and the cascade toggle,
// both of which filter edges by owner_id / visibility.
CREATE INDEX related_to_owner_visibility IF NOT EXISTS
FOR ()-[r:RELATED_TO]-() ON (r.owner_id, r.visibility);
