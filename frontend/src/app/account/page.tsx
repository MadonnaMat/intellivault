import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { AccountView } from "./account-view";
import { currentUser, currentUserCredentials } from "@/lib/session";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Account — IntelliVault" };

export default async function AccountPage() {
  const user = await currentUser();
  if (!user) redirect("/login");

  const credentials = (await currentUserCredentials()) ?? [];
  return <AccountView user={user} credentials={credentials} />;
}
