import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { currentUser } from "@/lib/session";
import { LoginBox } from "./login-box";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Sign in — IntelliVault" };

export default async function LoginPage() {
  if (await currentUser()) redirect("/");
  return <LoginBox />;
}
