import Link from "next/link";
import { redirect } from "next/navigation";
import { LogoutButton } from "./logout-button";
import { currentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function Home() {
  const user = await currentUser();
  if (!user) redirect("/login");

  return (
    <main>
      <h1>IntelliVault</h1>
      <p className="subtitle">
        Signed in as {user.display_name} ({user.email}).
      </p>
      <p>
        <Link href="/account" data-testid="account-link">
          Account &amp; passkeys
        </Link>
      </p>
      <p>
        <Link href="/graph" data-testid="graph-link">
          Knowledge graph
        </Link>
      </p>
      <LogoutButton />
    </main>
  );
}
