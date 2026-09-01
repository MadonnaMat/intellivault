"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Button, Card, Typography } from "antd";
import { loginPasskey } from "@/lib/auth";

export function LoginBox() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onLogin() {
    setLoading(true);
    setError(null);
    const result = await loginPasskey();
    setLoading(false);
    if (result.ok) {
      router.push("/");
      router.refresh();
    } else {
      setError(result.error ?? "Sign in failed");
    }
  }

  return (
    <main className="auth-shell">
      <Card title="Sign in to IntelliVault" data-testid="login-box" style={{ width: 360 }}>
        <Typography.Paragraph type="secondary">
          Use the passkey stored on this device.
        </Typography.Paragraph>

        {error && (
          <Alert
            data-testid="login-error"
            type="error"
            showIcon
            title={error}
            style={{ marginBottom: 16 }}
          />
        )}

        <Button
          type="primary"
          block
          loading={loading}
          onClick={onLogin}
          data-testid="login-submit"
        >
          Sign in with a passkey
        </Button>

        <Typography.Paragraph
          style={{ marginTop: 16, marginBottom: 0, textAlign: "center" }}
        >
          <Link href="/register" data-testid="register-link">
            Create an account
          </Link>
        </Typography.Paragraph>
      </Card>
    </main>
  );
}
