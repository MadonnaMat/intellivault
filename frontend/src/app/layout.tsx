import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AntdRegistry } from "@ant-design/nextjs-registry";
import { ConfigProvider } from "antd";
import { theme } from "./theme";
import "./globals.css";

export const metadata: Metadata = {
  title: "IntelliVault",
  description: "Collaborative intelligence vault",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AntdRegistry>
          <ConfigProvider theme={theme}>{children}</ConfigProvider>
        </AntdRegistry>
      </body>
    </html>
  );
}
