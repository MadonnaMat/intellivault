// SECURITY: entity_id already comes from this run's own just-created entity,
// but owner_id is still bound here per the blanket rule every :Entity-touching
// query follows — matching by id alone would let a caller attach sources to
// another user's entity if this were ever called with an untrusted id.
//
// Source nodes are shared, ownerless, and always public — a URL is public web
// data, not a user's private fact, so deduping only by url (never by owner)
// is the whole point of this model; two users researching the same page merge
// onto the same Source node with no conflict. Only the SOURCED_FROM edge
// carries privacy, mirroring its Entity endpoint (an entity is always private
// when this first runs, since app.agent.nodes.commit always creates entities
// private) — kept in sync afterwards by sync_entity_sources.cypher whenever a
// citing entity's visibility flips.
MATCH (e:Entity {id: $entity_id, owner_id: $owner_id})
UNWIND $urls AS url
MERGE (s:Source {url: url})
ON CREATE SET s.fetched_at = datetime()
MERGE (e)-[r:SOURCED_FROM]->(s)
SET r.visibility = e.visibility
