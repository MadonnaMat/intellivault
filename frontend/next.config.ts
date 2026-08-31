import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a minimal standalone server bundle for the Docker image.
  output: "standalone",
  // antd + its deps ship ESM that the standalone server bundle otherwise
  // mis-resolves ("Element type is invalid").
  transpilePackages: [
    "antd",
    "@ant-design/icons",
    "@ant-design/icons-svg",
    "@ant-design/nextjs-registry",
    "@ant-design/cssinjs",
    "rc-util",
    "rc-pagination",
    "rc-picker",
    "@rc-component/util",
  ],
};

export default nextConfig;
