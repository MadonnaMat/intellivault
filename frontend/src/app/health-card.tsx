"use client";

import { useState } from "react";
import { ReloadOutlined } from "@ant-design/icons";
import { Alert, Badge, Button, Card, List, Space, Tag, Typography } from "antd";
import type { BadgeProps } from "antd";
import {
  fetchHealth,
  publicBackendUrl,
  type HealthResult,
  type HealthState,
  type ServiceStatus,
} from "@/lib/health";

const STATE_BADGE: Record<HealthState, BadgeProps["status"]> = {
  ok: "success",
  degraded: "warning",
  down: "error",
};

function serviceLabel(service: ServiceStatus): { text: string; color: string } {
  if (!service.ok) return { text: "down", color: "error" };
  if (service.degraded) return { text: "degraded", color: "warning" };
  return { text: "ok", color: "success" };
}

export function HealthCard({ initial }: { initial: HealthResult }) {
  const [result, setResult] = useState<HealthResult>(initial);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    setResult(await fetchHealth(publicBackendUrl));
    setLoading(false);
  }

  const overall = result.data?.status ?? "down";
  const overallText = result.data ? result.data.status : "unreachable";

  return (
    <Card
      data-testid="health-card"
      title={
        <Badge
          status={STATE_BADGE[overall]}
          text={<span data-testid="health-status">{overallText}</span>}
        />
      }
      extra={
        <Button
          data-testid="refresh-button"
          icon={<ReloadOutlined />}
          onClick={refresh}
          loading={loading}
          size="small"
        >
          Refresh
        </Button>
      }
    >
      {result.error && (
        <Alert
          data-testid="health-error"
          type="error"
          showIcon
          message="Could not reach the backend"
          description={result.error}
          style={{ marginBottom: result.data ? 16 : 0 }}
        />
      )}

      {result.data && (
        <List
          size="small"
          dataSource={result.data.services}
          renderItem={(service) => {
            const label = serviceLabel(service);
            return (
              <List.Item
                data-testid={`service-${service.name}`}
                actions={[
                  <Typography.Text
                    type="secondary"
                    key="detail"
                    data-testid={`service-${service.name}-detail`}
                  >
                    {service.detail} · {Math.round(service.latency_ms)} ms
                  </Typography.Text>,
                ]}
              >
                <Space>
                  <Tag color={label.color} data-testid={`service-${service.name}-status`}>
                    {label.text}
                  </Tag>
                  <Typography.Text strong>{service.name}</Typography.Text>
                </Space>
              </List.Item>
            );
          }}
        />
      )}
    </Card>
  );
}
