"use client";

import type { ReactNode } from "react";
import { Alert, Card } from "antd";

/** The centered card shell shared by the /login and /register pages. */
export function AuthCard({
  title,
  cardTestid,
  errorTestid,
  error,
  width = 360,
  children,
  footer,
}: {
  title: string;
  cardTestid: string;
  errorTestid: string;
  error: string | null;
  width?: number;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <main className="auth-shell">
      <Card title={title} data-testid={cardTestid} style={{ width }}>
        {error && (
          <Alert
            data-testid={errorTestid}
            type="error"
            showIcon
            title={error}
            style={{ marginBottom: 16 }}
          />
        )}
        {children}
        <div style={{ marginTop: 16, textAlign: "center" }}>{footer}</div>
      </Card>
    </main>
  );
}
