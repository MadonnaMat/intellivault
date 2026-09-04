import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { RunsListView } from "./runs-list-view";
import { currentAgentRuns, currentUser } from "@/lib/session";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Agent Runs — IntelliVault" };

export default async function RunsPage() {
  const [user, runs] = await Promise.all([currentUser(), currentAgentRuns()]);
  if (!user) redirect("/login");
  return <RunsListView user={user} runs={runs ?? []} />;
}
