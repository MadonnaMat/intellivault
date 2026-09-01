import type { Metadata } from "next";
import { LoginBox } from "./login-box";

export const metadata: Metadata = { title: "Sign in — IntelliVault" };

export default function LoginPage() {
  return <LoginBox />;
}
