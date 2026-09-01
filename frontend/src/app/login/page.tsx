import type { Metadata } from "next";
import { redirectIfAuthenticated } from "@/lib/session";
import { LoginBox } from "./login-box";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Sign in — IntelliVault" };

export default async function LoginPage() {
  await redirectIfAuthenticated();
  return <LoginBox />;
}
