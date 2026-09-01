import type { Metadata } from "next";
import { redirectIfAuthenticated } from "@/lib/session";
import { RegisterForm } from "./register-form";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Create an account — IntelliVault" };

export default async function RegisterPage() {
  await redirectIfAuthenticated();
  return <RegisterForm />;
}
