import type { ThemeConfig } from "antd";

// Matches the accent color already hardcoded in graph-diagram.tsx's STYLESHEET.
const ACCENT = "#1677ff";

export const theme: ThemeConfig = {
  token: {
    colorPrimary: ACCENT,
    borderRadius: 8,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  },
  components: {
    Layout: {
      headerBg: "#ffffff",
      headerHeight: 56,
      headerPadding: "0 24px",
      bodyBg: "#f5f5f5",
    },
  },
};
