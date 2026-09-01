"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Button, Card, Form, Input, List, Modal, Space, Typography } from "antd";
import {
  addPasskey,
  removeCredential,
  updateAccount,
  type CredentialSummary,
  type SessionUser,
} from "@/lib/auth";
import { LogoutButton } from "../logout-button";

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
}: {
  user: SessionUser;
  credentials: CredentialSummary[];
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [passkeyName, setPasskeyName] = useState("");
  const [addingPasskey, setAddingPasskey] = useState(false);

  async function onSaveProfile(values: ProfileValues) {
    setSavingProfile(true);
    setError(null);
    const result = await updateAccount({
      email: values.email,
      displayName: values.display_name,
    });
    setSavingProfile(false);
    if (result.ok) router.refresh();
    else setError(result.error ?? "Could not save your profile");
  }

  async function onAddPasskey() {
    setAddingPasskey(true);
    setError(null);
    const result = await addPasskey(passkeyName.trim() || "Passkey");
    setAddingPasskey(false);
    setAddOpen(false);
    setPasskeyName("");
    if (result.ok) router.refresh();
    else setError(result.error ?? "Could not add the passkey");
  }

  async function onRemove(id: string) {
    setError(null);
    const result = await removeCredential(id);
    if (result.ok) router.refresh();
    else setError(result.error ?? "Could not remove the passkey");
  }

  return (
    <main>
      <h1>Account &amp; passkeys</h1>
      <Space style={{ marginBottom: 16 }}>
        <Link href="/">Back to home</Link>
        <LogoutButton />
      </Space>

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
            loading={savingProfile}
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

      <Modal
        open={addOpen}
        title="Name this passkey"
        okText="Continue"
        okButtonProps={{ loading: addingPasskey }}
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
    </main>
  );
}
