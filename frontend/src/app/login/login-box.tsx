"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button, Typography } from "antd";
import { loginPasskey } from "@/lib/auth";
import { useAsyncAction } from "@/lib/use-async-action";
import { AuthCard } from "../auth-card";

export function LoginBox() {
  const router = useRouter();
  const { loading, error, run } = useAsyncAction();

  function onLogin() {
    return run(loginPasskey, {
      fallback: "Sign in failed",
      onSuccess: () => {
        router.push("/");
        router.refresh();
      },
    });
  }

  return (
    <AuthCard
      title="Sign in to IntelliVault"
      cardTestid="login-box"
      errorTestid="login-error"
      error={error}
      footer={
        <Link href="/register" data-testid="register-link">
          Create an account
        </Link>
      }
    >
      <Typography.Paragraph type="secondary">
        Use the passkey stored on this device.
      </Typography.Paragraph>
      <Button
        type="primary"
        block
        loading={loading}
        onClick={onLogin}
        data-testid="login-submit"
      >
        Sign in with a passkey
      </Button>
    </AuthCard>
  );
}
