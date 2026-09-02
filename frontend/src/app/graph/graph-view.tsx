"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import type { SessionUser } from "@/lib/auth";
import {
  createEntity,
  createRelationship,
  seedSampleGraph,
  setEntityVisibility,
  type GraphEntity,
  type GraphRelationship,
  type GraphView as GraphData,
  type Visibility,
} from "@/lib/graph";
import { useAsyncAction } from "@/lib/use-async-action";
import { LogoutButton } from "../logout-button";

// Cytoscape is ~200 kB and touches `window`; load it only in the browser.
const GraphDiagram = dynamic(
  () => import("./graph-diagram").then((mod) => mod.GraphDiagram),
  { ssr: false, loading: () => <p>Loading diagram…</p> },
);

const VISIBILITY_OPTIONS = [
  { value: "private", label: "Private" },
  { value: "public", label: "Public" },
];

function visibilityTag(visibility: Visibility) {
  return (
    <Tag color={visibility === "public" ? "green" : "default"}>{visibility}</Tag>
  );
}

interface EntityFormValues {
  name: string;
  kind: string;
  visibility: Visibility;
}

interface RelationshipFormValues {
  from_id: string;
  to_id: string;
  kind: string;
  visibility: Visibility;
}

export function GraphView({ user, initial }: { user: SessionUser; initial: GraphData }) {
  const router = useRouter();
  const { loading, error, run } = useAsyncAction();
  const [entityForm] = Form.useForm<EntityFormValues>();
  const [relForm] = Form.useForm<RelationshipFormValues>();
  const [cascade, setCascade] = useState<Record<string, boolean>>({});

  const refresh = () => router.refresh();
  const entities = initial.entities;
  const relationships = initial.relationships ?? [];
  const nameById = useMemo(
    () => new Map(entities.map((entity) => [entity.id, entity.name])),
    [entities],
  );

  function toggleVisibility(entity: GraphEntity) {
    const next: Visibility = entity.visibility === "public" ? "private" : "public";
    return run(
      () => setEntityVisibility(entity.id, { visibility: next, cascade: !!cascade[entity.id] }),
      { fallback: "Could not change visibility", onSuccess: refresh },
    );
  }

  function onCreateEntity(values: EntityFormValues) {
    return run(() => createEntity({ ...values, attributes: {} }), {
      fallback: "Could not create the entity",
      onSuccess: () => {
        entityForm.resetFields();
        refresh();
      },
    });
  }

  function onCreateRelationship(values: RelationshipFormValues) {
    return run(() => createRelationship(values), {
      fallback: "Could not create the relationship",
      onSuccess: () => {
        relForm.resetFields();
        refresh();
      },
    });
  }

  function onLoadSample() {
    return run(() => seedSampleGraph(), {
      fallback: "Could not load the sample graph",
      onSuccess: refresh,
    });
  }

  const entityColumns = [
    { title: "Name", dataIndex: "name", key: "name" },
    { title: "Kind", dataIndex: "kind", key: "kind" },
    {
      title: "Visibility",
      key: "visibility",
      render: (_: unknown, entity: GraphEntity) => visibilityTag(entity.visibility),
    },
    {
      title: "Owner",
      key: "owner",
      render: (_: unknown, entity: GraphEntity) =>
        entity.owner_id === user.id ? <Tag color="blue">you</Tag> : <Tag>shared</Tag>,
    },
    {
      title: "Change visibility",
      key: "actions",
      render: (_: unknown, entity: GraphEntity) => {
        if (entity.owner_id !== user.id) return <Typography.Text type="secondary">—</Typography.Text>;
        return (
          <Space>
            <Switch
              data-testid={`entity-${entity.id}-visibility`}
              checked={entity.visibility === "public"}
              loading={loading}
              onChange={() => toggleVisibility(entity)}
            />
            <Checkbox
              data-testid={`entity-${entity.id}-cascade`}
              checked={!!cascade[entity.id]}
              onChange={(event) =>
                setCascade((current) => ({ ...current, [entity.id]: event.target.checked }))
              }
            >
              cascade to connected
            </Checkbox>
          </Space>
        );
      },
    },
  ];

  const relationshipColumns = [
    {
      title: "From",
      key: "from",
      render: (_: unknown, rel: GraphRelationship) =>
        nameById.get(rel.from_id) ?? rel.from_id,
    },
    { title: "Kind", dataIndex: "kind", key: "kind" },
    {
      title: "To",
      key: "to",
      render: (_: unknown, rel: GraphRelationship) =>
        nameById.get(rel.to_id) ?? rel.to_id,
    },
    {
      title: "Visibility",
      key: "visibility",
      render: (_: unknown, rel: GraphRelationship) =>
        visibilityTag(rel.visibility),
    },
  ];

  const entityOptions = entities.map((entity) => ({ value: entity.id, label: entity.name }));

  return (
    <main className="graph-shell">
      <h1>Knowledge graph</h1>
      <Space style={{ marginBottom: 16 }}>
        <Link href="/" data-testid="home-link">
          Back to home
        </Link>
        <LogoutButton />
      </Space>

      {error && (
        <Alert
          data-testid="graph-error"
          type="error"
          showIcon
          title={error}
          style={{ marginBottom: 16 }}
        />
      )}

      <Card
        title="Graph"
        data-testid="graph-diagram-card"
        style={{ marginBottom: 16 }}
        extra={
          <Button data-testid="load-sample-graph" onClick={onLoadSample} loading={loading}>
            Load sample graph
          </Button>
        }
      >
        <GraphDiagram
          entities={entities}
          relationships={relationships}
          ownerId={user.id}
          onToggle={toggleVisibility}
        />
      </Card>

      <Card title="Entities" data-testid="entities-card" style={{ marginBottom: 16 }}>
        <Form
          form={entityForm}
          layout="inline"
          initialValues={{ visibility: "private" }}
          onFinish={onCreateEntity}
          style={{ marginBottom: 16, rowGap: 8, flexWrap: "wrap" }}
        >
          <Form.Item name="name" rules={[{ required: true, message: "Name" }]}>
            <Input placeholder="Name" data-testid="create-entity-name" />
          </Form.Item>
          <Form.Item name="kind" rules={[{ required: true, message: "Kind" }]}>
            <Input placeholder="Kind (e.g. person)" data-testid="create-entity-kind" />
          </Form.Item>
          <Form.Item name="visibility">
            <Select
              options={VISIBILITY_OPTIONS}
              data-testid="create-entity-visibility"
              style={{ width: 120 }}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} data-testid="create-entity-submit">
            Add entity
          </Button>
        </Form>
        <Table
          rowKey="id"
          size="small"
          dataSource={entities}
          columns={entityColumns}
          pagination={false}
          locale={{ emptyText: "No entities" }}
          onRow={(entity) => ({ "data-testid": `entity-row-${entity.id}` }) as object}
        />
      </Card>

      <Card title="Relationships" data-testid="relationships-card">
        <Form
          form={relForm}
          layout="inline"
          initialValues={{ visibility: "private" }}
          onFinish={onCreateRelationship}
          style={{ marginBottom: 16, rowGap: 8, flexWrap: "wrap" }}
        >
          <Form.Item name="from_id" rules={[{ required: true, message: "From" }]}>
            <Select
              placeholder="From"
              options={entityOptions}
              data-testid="create-rel-from"
              style={{ width: 160 }}
            />
          </Form.Item>
          <Form.Item name="kind" rules={[{ required: true, message: "Kind" }]}>
            <Input placeholder="Kind (e.g. employs)" data-testid="create-rel-kind" />
          </Form.Item>
          <Form.Item name="to_id" rules={[{ required: true, message: "To" }]}>
            <Select
              placeholder="To"
              options={entityOptions}
              data-testid="create-rel-to"
              style={{ width: 160 }}
            />
          </Form.Item>
          <Form.Item name="visibility">
            <Select
              options={VISIBILITY_OPTIONS}
              data-testid="create-rel-visibility"
              style={{ width: 120 }}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} data-testid="create-rel-submit">
            Connect
          </Button>
        </Form>
        <Table
          rowKey="id"
          size="small"
          dataSource={relationships}
          columns={relationshipColumns}
          pagination={false}
          locale={{ emptyText: "No relationships" }}
          onRow={(rel) => ({ "data-testid": `rel-row-${rel.id}` }) as object}
        />
      </Card>
    </main>
  );
}
