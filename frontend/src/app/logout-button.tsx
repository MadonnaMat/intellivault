"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "antd";
import { logout } from "@/lib/auth";

export function LogoutButton() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function onLogout() {
    setLoading(true);
    await logout();
    router.push("/login");
    router.refresh();
  }

  return (
    <Button data-testid="logout-button" onClick={onLogout} loading={loading}>
      Log out
    </Button>
  );
}
