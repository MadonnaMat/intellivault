import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// antd's Table measures the scrollbar via getComputedStyle(el, pseudoElt),
// which jsdom logs as "Not implemented". Drop the pseudo-element arg.
const realGetComputedStyle = window.getComputedStyle.bind(window);
window.getComputedStyle = ((element: Element) =>
  realGetComputedStyle(element)) as typeof window.getComputedStyle;

// antd reads matchMedia at render; jsdom doesn't implement it.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});
