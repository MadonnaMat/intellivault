import { redirect } from "next/navigation";
import { AppShell } from "./app-shell";
import { ChatView } from "./chat/chat-view";
import { currentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function Home() {
  const user = await currentUser();
  if (!user) redirect("/login");

  return (
    <AppShell user={user}>
      <ChatView user={user} />
    </AppShell>
  );
}
