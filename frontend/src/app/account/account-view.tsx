"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Button, Card, Form, Input, List, Modal, Typography } from "antd";
import type { HealthResult } from "@/lib/health";
import {
  addPasskey,
  removeCredential,
  updateAccount,
  type CredentialSummary,
  type SessionUser,
} from "@/lib/auth";
import { useAsyncAction } from "@/lib/use-async-action";
import { AppShell } from "../app-shell";
import { HealthCard } from "../health-card";

interface ProfileValues {
  email: string;
  display_name: string;
}

function describeCredential(cred: CredentialSummary): string {
  const added = `Added ${new Date(cred.created_at).toLocaleDateString()}`;
  if (!cred.last_used_at) return added;
  return `${added} · last used ${new Date(cred.last_used_at).toLocaleDateString()}`;
}

export function AccountView({
  user,
  credentials,
  health,
}: {
  user: SessionUser;
  credentials: CredentialSummary[];
  health: HealthResult;
}) {
  const router = useRouter();
  const { loading, error, run } = useAsyncAction();
  const [addOpen, setAddOpen] = useState(false);
  const [passkeyName, setPasskeyName] = useState("");

  const refresh = () => router.refresh();

  function onSaveProfile(values: ProfileValues) {
    return run(
      () => updateAccount({ email: values.email, displayName: values.display_name }),
      { fallback: "Could not save your profile", onSuccess: refresh },
    );
  }

  async function onAddPasskey() {
    await run(() => addPasskey(passkeyName.trim() || "Passkey"), {
      fallback: "Could not add the passkey",
      onSuccess: refresh,
    });
    setAddOpen(false);
    setPasskeyName("");
  }

  function onRemove(id: string) {
    return run(() => removeCredential(id), {
      fallback: "Could not remove the passkey",
      onSuccess: refresh,
    });
  }

  return (
    <AppShell user={user}>
      <div className="page-shell">
        <h1>Account &amp; passkeys</h1>

        {error && (
          <Alert
            data-testid="account-error"
            type="error"
            showIcon
            title={error}
            style={{ marginBottom: 16 }}
          />
        )}

        <Card title="Profile" data-testid="account-view" style={{ marginBottom: 16 }}>
          <Form
            layout="vertical"
            requiredMark={false}
            initialValues={{ email: user.email, display_name: user.display_name }}
            onFinish={onSaveProfile}
          >
            <Form.Item
              label="Email"
              name="email"
              rules={[{ required: true, type: "email", message: "Enter a valid email" }]}
            >
              <Input data-testid="account-email" />
            </Form.Item>
            <Form.Item
              label="Display name"
              name="display_name"
              rules={[{ required: true, message: "Enter a display name" }]}
            >
              <Input data-testid="account-display-name" />
            </Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              data-testid="account-save"
            >
              Save
            </Button>
          </Form>
        </Card>

        <Card
          title="Passkeys"
          extra={
            <Button data-testid="add-passkey-button" onClick={() => setAddOpen(true)}>
              Add a passkey
            </Button>
          }
        >
          <List
            data-testid="passkeys-list"
            dataSource={credentials}
            locale={{ emptyText: "No passkeys" }}
            renderItem={(cred) => (
              <List.Item
                data-testid={`credential-${cred.id}`}
                actions={[
                  <Button
                    key="remove"
                    danger
                    size="small"
                    loading={loading}
                    disabled={credentials.length <= 1}
                    data-testid={`credential-${cred.id}-remove`}
                    onClick={() => onRemove(cred.id)}
                  >
                    Remove
                  </Button>,
                ]}
              >
                <List.Item.Meta title={cred.name} description={describeCredential(cred)} />
              </List.Item>
            )}
          />
        </Card>

        <div style={{ marginTop: 16 }}>
          <HealthCard initial={health} />
        </div>

        <Modal
          open={addOpen}
          title="Name this passkey"
          okText="Continue"
          okButtonProps={{ loading }}
          onOk={onAddPasskey}
          onCancel={() => setAddOpen(false)}
        >
          <Typography.Paragraph type="secondary">
            Your browser will then prompt you to create a passkey on this device.
          </Typography.Paragraph>
          <Input
            data-testid="add-passkey-name"
            placeholder="e.g. Work laptop"
            value={passkeyName}
            onChange={(event) => setPasskeyName(event.target.value)}
            onPressEnter={onAddPasskey}
          />
        </Modal>
      </div>
    </AppShell>
  );
}
