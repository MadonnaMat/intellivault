"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  Popconfirm,
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
  deleteEntity,
  deleteRelationship,
  seedSampleGraph,
  setEntityVisibility,
  type GraphEntity,
  type GraphRelationship,
  type GraphView as GraphData,
  type Visibility,
} from "@/lib/graph";
import { useAsyncAction } from "@/lib/use-async-action";
import { AppShell } from "../app-shell";

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
  const { loading, error, setError, run } = useAsyncAction();
  const [entityForm] = Form.useForm<EntityFormValues>();
  const [relForm] = Form.useForm<RelationshipFormValues>();
  const [cascade, setCascade] = useState<Record<string, boolean>>({});
  // The one entity whose visibility toggle is in flight — so toggling A doesn't
  // spin B's and C's switches or lock the create forms.
  const [pendingId, setPendingId] = useState<string | null>(null);

  const refresh = () => router.refresh();
  const entities = initial.entities;
  const relationships = initial.relationships ?? [];
  const entityById = useMemo(
    () => new Map(entities.map((entity) => [entity.id, entity])),
    [entities],
  );
  const nameById = useMemo(
    () => new Map(entities.map((entity) => [entity.id, entity.name])),
    [entities],
  );

  // A relationship can't be more visible than its endpoints: "public" is only
  // offered when both selected entities are public.
  const relFromId = Form.useWatch("from_id", relForm);
  const relToId = Form.useWatch("to_id", relForm);
  const relCanBePublic =
    entityById.get(relFromId)?.visibility === "public" &&
    entityById.get(relToId)?.visibility === "public";

  useEffect(() => {
    if (!relCanBePublic) relForm.setFieldValue("visibility", "private");
  }, [relCanBePublic, relForm]);
  const ownedEntityIds = useMemo(
    () => new Set(entities.filter((e) => e.owner_id === user.id).map((e) => e.id)),
    [entities, user.id],
  );
  const canDeleteRelationship = (rel: GraphRelationship) =>
    rel.owner_id === user.id ||
    ownedEntityIds.has(rel.from_id) ||
    ownedEntityIds.has(rel.to_id);

  // cascadeOverride comes from the diagram's shift-click; the table's Switch
  // calls this with no second argument, falling back to its own checkbox.
  async function toggleVisibility(entity: GraphEntity, cascadeOverride?: boolean) {
    const next: Visibility = entity.visibility === "public" ? "private" : "public";
    setPendingId(entity.id);
    setError(null);
    const result = await setEntityVisibility(entity.id, {
      visibility: next,
      cascade: cascadeOverride ?? !!cascade[entity.id],
    });
    setPendingId(null);
    if (result.ok) refresh();
    else setError(result.error ?? "Could not change visibility");
  }

  function onDeleteEntity(id: string) {
    return run(() => deleteEntity(id), {
      fallback: "Could not delete the entity",
      onSuccess: refresh,
    });
  }

  function onDeleteRelationship(id: string) {
    return run(() => deleteRelationship(id), {
      fallback: "Could not delete the relationship",
      onSuccess: refresh,
    });
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
    const visibility = relCanBePublic ? values.visibility : "private";
    return run(() => createRelationship({ ...values, visibility }), {
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
              loading={pendingId === entity.id}
              disabled={pendingId !== null && pendingId !== entity.id}
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
    {
      title: "",
      key: "delete",
      render: (_: unknown, entity: GraphEntity) =>
        entity.owner_id === user.id ? (
          <Popconfirm
            title="Delete this entity and its relationships?"
            okText="Delete"
            okButtonProps={{ danger: true }}
            onConfirm={() => onDeleteEntity(entity.id)}
          >
            <Button danger size="small" data-testid={`entity-${entity.id}-delete`}>
              Delete
            </Button>
          </Popconfirm>
        ) : null,
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
    {
      title: "",
      key: "delete",
      render: (_: unknown, rel: GraphRelationship) =>
        canDeleteRelationship(rel) ? (
          <Popconfirm
            title="Delete this relationship?"
            okText="Delete"
            okButtonProps={{ danger: true }}
            onConfirm={() => onDeleteRelationship(rel.id)}
          >
            <Button danger size="small" data-testid={`rel-${rel.id}-delete`}>
              Delete
            </Button>
          </Popconfirm>
        ) : null,
    },
  ];

  const entityOptions = entities.map((entity) => ({ value: entity.id, label: entity.name }));

  return (
    <AppShell user={user}>
      <div className="page-shell graph-shell">
        <h1>Knowledge graph</h1>

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
            <Button
              data-testid="load-sample-graph"
              onClick={onLoadSample}
              loading={loading}
              disabled={entities.length > 0}
              title={
                entities.length > 0
                  ? "Clear the graph first — the sample would be added on top"
                  : undefined
              }
            >
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
                disabled={!relCanBePublic}
                title={
                  relCanBePublic
                    ? undefined
                    : "A relationship can only be public when both entities are public"
                }
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
      </div>
    </AppShell>
  );
}
