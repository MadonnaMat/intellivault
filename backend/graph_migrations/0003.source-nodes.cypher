// 0003 — Source nodes for entity provenance
//
// The agent loop links each entity it commits to the Source node(s) for every
// URL its run fetched (app.graph.service.attach_sources), so a user can trace
// an entity back to the page(s) it came from — surfaced as a Sources column
// on the graph page. A Source carries no owner_id and no visibility of its
// own: a URL is public web data, not a user's private fact, so the same
// Source node is shared across every user and run that cites it — the
// uniqueness constraint backs the create-or-match MERGE in
// attach_sources.cypher so the same URL is never duplicated. Only the
// SOURCED_FROM edge is privacy-scoped, mirroring its Entity endpoint's
// visibility (kept in sync by sync_entity_sources.cypher whenever a citing
// entity's own visibility flips).
CREATE CONSTRAINT source_url_unique IF NOT EXISTS
FOR (s:Source) REQUIRE s.url IS UNIQUE;
