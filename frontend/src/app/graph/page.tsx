import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { GraphView } from "./graph-view";
import { currentGraph, currentUser } from "@/lib/session";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Knowledge graph — IntelliVault" };

export default async function GraphPage() {
  const [user, graph] = await Promise.all([currentUser(), currentGraph()]);
  if (!user) redirect("/login");
  return (
    <GraphView user={user} initial={graph ?? { entities: [], relationships: [] }} />
  );
}
