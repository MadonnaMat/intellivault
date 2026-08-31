// Lightweight liveness route for the container healthcheck — no backend call.
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" });
}
