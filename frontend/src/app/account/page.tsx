import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { AccountView } from "./account-view";
import { fetchHealthFromServer } from "@/lib/health";
import { currentUser, currentUserCredentials } from "@/lib/session";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Account — IntelliVault" };

export default async function AccountPage() {
  const [user, credentials, health] = await Promise.all([
    currentUser(),
    currentUserCredentials(),
    fetchHealthFromServer(),
  ]);
  if (!user) redirect("/login");
  return <AccountView user={user} credentials={credentials ?? []} health={health} />;
}
