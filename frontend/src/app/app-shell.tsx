"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Layout, Space, Typography } from "antd";
import type { SessionUser } from "@/lib/auth";
import { LogoutButton } from "./logout-button";

const NAV_ITEMS = [
  { href: "/", label: "Chat", testId: "nav-chat" },
  { href: "/graph", label: "Graph", testId: "nav-graph" },
  { href: "/runs", label: "Agent Runs", testId: "nav-runs" },
  { href: "/account", label: "Account", testId: "nav-account" },
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ user, children }: { user: SessionUser; children: ReactNode }) {
  const pathname = usePathname();

  return (
    <Layout data-testid="app-shell" style={{ minHeight: "100dvh" }}>
      <Layout.Header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid #f0f0f0",
        }}
      >
        <Space size="large">
          <Typography.Text strong style={{ fontSize: 16 }}>
            IntelliVault
          </Typography.Text>
          <Space size="middle" data-testid="app-nav">
            {NAV_ITEMS.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  data-testid={item.testId}
                  aria-current={active ? "page" : undefined}
                  style={{
                    color: active ? "#1677ff" : "rgba(0, 0, 0, 0.88)",
                    fontWeight: active ? 600 : 400,
                  }}
                >
                  {item.label}
                </Link>
              );
            })}
          </Space>
        </Space>
        <Space size="middle">
          <Typography.Text type="secondary" data-testid="app-shell-user">
            {user.display_name} ({user.email})
          </Typography.Text>
          <LogoutButton />
        </Space>
      </Layout.Header>
      <Layout.Content>{children}</Layout.Content>
    </Layout>
  );
}
