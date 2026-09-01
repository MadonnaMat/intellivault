/** Where the browser reaches the backend (client components, baked in at build). */
export const publicBackendUrl =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

/** Where server components reach the backend (in-network hostname under compose). */
export const serverBackendUrl = process.env.BACKEND_URL ?? publicBackendUrl;
