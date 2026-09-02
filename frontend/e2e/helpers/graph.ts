import neo4j from "neo4j-driver";

/**
 * Bolt URL + password for the Neo4j the running backend uses. The e2e run owns
 * this data, same as `resetDb` owns the Postgres side.
 */
const url = process.env.E2E_NEO4J_URL ?? "bolt://localhost:7687";
const password = process.env.NEO4J_PASSWORD ?? "intellivault";

/**
 * Delete every domain node (`:Entity` and its relationships). Leaves the schema
 * and the `:_GraphMigration` bookkeeping nodes alone.
 */
export async function resetGraph(): Promise<void> {
  const driver = neo4j.driver(url, neo4j.auth.basic("neo4j", password));
  try {
    await driver.executeQuery("MATCH (n:Entity) DETACH DELETE n");
  } finally {
    await driver.close();
  }
}
