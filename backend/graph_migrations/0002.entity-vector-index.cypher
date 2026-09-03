// 0002 — vector index over Entity embeddings
//
// The agent loop (backend/app/agent/) embeds each entity it creates with the
// Ollama embedding model and stores the vector on e.embedding. This index backs
// db.index.vector.queryNodes(), which the agent's survey step uses to pull only
// the entities relevant to a run's topic instead of the whole visible graph.
//
// 768 = the dimensionality of `nomic-embed-text` (OLLAMA_EMBED_MODEL). Switching
// to an embedding model with a different width needs a new migration that drops
// and recreates this index (and a re-embed of existing entities).
CREATE VECTOR INDEX entity_embedding IF NOT EXISTS
FOR (e:Entity) ON (e.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 768,
  `vector.similarity_function`: 'cosine'
} };
