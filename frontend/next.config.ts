import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a minimal standalone server bundle for the Docker image.
  output: "standalone",
};

export default nextConfig;
