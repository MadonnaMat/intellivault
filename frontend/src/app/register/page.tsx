import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { currentUser } from "@/lib/session";
import { RegisterForm } from "./register-form";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Create an account — IntelliVault" };

export default async function RegisterPage() {
  if (await currentUser()) redirect("/");
  return <RegisterForm />;
}
