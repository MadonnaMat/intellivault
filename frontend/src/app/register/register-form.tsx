"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Button, Card, Form, Input, Typography } from "antd";
import { registerPasskey } from "@/lib/auth";

interface Values {
  email: string;
  display_name: string;
}

export function RegisterForm() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onFinish(values: Values) {
    setLoading(true);
    setError(null);
    const result = await registerPasskey(values.email, values.display_name);
    setLoading(false);
    if (result.ok) {
      router.push("/");
      router.refresh();
    } else {
      setError(result.error ?? "Registration failed");
    }
  }

  return (
    <main className="auth-shell">
      <Card title="Create your account" data-testid="register-form" style={{ width: 380 }}>
        {error && (
          <Alert
            data-testid="register-error"
            type="error"
            showIcon
            title={error}
            style={{ marginBottom: 16 }}
          />
        )}

        <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            label="Email"
            name="email"
            rules={[{ required: true, type: "email", message: "Enter a valid email" }]}
          >
            <Input data-testid="register-email" autoComplete="username" />
          </Form.Item>

          <Form.Item
            label="Display name"
            name="display_name"
            rules={[{ required: true, message: "Enter a display name" }]}
          >
            <Input data-testid="register-display-name" />
          </Form.Item>

          <Button
            type="primary"
            htmlType="submit"
            block
            loading={loading}
            data-testid="register-submit"
          >
            Create account with a passkey
          </Button>
        </Form>

        <Typography.Paragraph
          style={{ marginTop: 16, marginBottom: 0, textAlign: "center" }}
        >
          <Link href="/login" data-testid="login-link">
            Already have an account? Sign in
          </Link>
        </Typography.Paragraph>
      </Card>
    </main>
  );
}
