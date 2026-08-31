"use client";

import { useState } from "react";
import {
  fetchHealth,
  publicBackendUrl,
  type HealthResult,
  type HealthState,
} from "@/lib/health";

const STATE_COLOR: Record<HealthState, string> = {
  ok: "var(--ok)",
  degraded: "var(--degraded)",
  down: "var(--down)",
};

function dotColor(result: HealthResult): string {
  if (!result.data) return "var(--down)";
  return STATE_COLOR[result.data.status];
}

export function HealthCard({ initial }: { initial: HealthResult }) {
  const [result, setResult] = useState<HealthResult>(initial);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    setResult(await fetchHealth(publicBackendUrl));
    setLoading(false);
  }

  return (
    <section
      style={{
        border: "1px solid var(--border)",
        background: "var(--card)",
        borderRadius: 12,
        padding: "1.25rem",
      }}
    >
      <header
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600 }}>
          <span
            aria-hidden
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: dotColor(result),
              display: "inline-block",
            }}
          />
          {result.data ? result.data.status : "unreachable"}
        </span>
        <button onClick={refresh} disabled={loading}>
          {loading ? "Checking…" : "Refresh"}
        </button>
      </header>

      {result.error && (
        <p style={{ color: "var(--down)", marginBottom: 0 }}>
          Could not reach the backend: {result.error}
        </p>
      )}

      {result.data && (
        <ul style={{ listStyle: "none", padding: 0, margin: "1rem 0 0" }}>
          {result.data.services.map((service) => (
            <li
              key={service.name}
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 12,
                padding: "0.5rem 0",
                borderTop: "1px solid var(--border)",
              }}
            >
              <span
                style={{
                  color: service.ok
                    ? service.degraded
                      ? "var(--degraded)"
                      : "var(--ok)"
                    : "var(--down)",
                }}
              >
                {service.ok ? (service.degraded ? "◐" : "●") : "○"} {service.name}
              </span>
              <span style={{ color: "var(--muted)" }}>
                {service.detail} · {Math.round(service.latency_ms)} ms
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
