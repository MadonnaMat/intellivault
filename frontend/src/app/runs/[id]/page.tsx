import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { RunDetailView } from "./run-detail-view";
import { currentAgentRun, currentUser } from "@/lib/session";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Agent Run — IntelliVault" };

export default async function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [user, run] = await Promise.all([currentUser(), currentAgentRun(id)]);
  if (!user) redirect("/login");
  // currentAgentRun returns null only for "not authenticated" (same cookie
  // check as currentUser, already handled above) — a missing/foreign run
  // takes the framework's not-found path from inside currentAgentRun itself.
  return <RunDetailView user={user} runId={id} initial={run!} />;
}
