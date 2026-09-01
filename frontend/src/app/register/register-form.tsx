"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button, Form, Input } from "antd";
import { registerPasskey } from "@/lib/auth";
import { useAsyncAction } from "@/lib/use-async-action";
import { AuthCard } from "../auth-card";

interface Values {
  email: string;
  display_name: string;
}

export function RegisterForm() {
  const router = useRouter();
  const { loading, error, run } = useAsyncAction();

  function onFinish(values: Values) {
    return run(() => registerPasskey(values.email, values.display_name), {
      fallback: "Registration failed",
      onSuccess: () => {
        router.push("/");
        router.refresh();
      },
    });
  }

  return (
    <AuthCard
      title="Create your account"
      cardTestid="register-form"
      errorTestid="register-error"
      error={error}
      width={380}
      footer={
        <Link href="/login" data-testid="login-link">
          Already have an account? Sign in
        </Link>
      }
    >
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
    </AuthCard>
  );
}
