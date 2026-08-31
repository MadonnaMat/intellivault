import { HealthCard } from "./health-card";
import { fetchHealthFromServer } from "@/lib/health";

export const dynamic = "force-dynamic";

export default async function Home() {
  const initial = await fetchHealthFromServer();

  return (
    <main>
      <h1>IntelliVault</h1>
      <p className="subtitle">
        Gateway health — Neo4j, Postgres, Arize-Phoenix and Ollama.
      </p>
      <HealthCard initial={initial} />
    </main>
  );
}
