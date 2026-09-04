import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// antd popovers (Popconfirm, Tooltip, Select dropdown) observe element size;
// jsdom has no ResizeObserver.
window.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// antd's Table measures the scrollbar via getComputedStyle(el, pseudoElt),
// which jsdom logs as "Not implemented". Drop the pseudo-element arg.
const realGetComputedStyle = window.getComputedStyle.bind(window);
window.getComputedStyle = ((element: Element) =>
  realGetComputedStyle(element)) as typeof window.getComputedStyle;

// assistant-ui's thread auto-scroll calls Element.scrollTo on a rAF tick,
// sometimes after a test has already torn its component down; jsdom has no
// scrollTo at all, which otherwise surfaces as an unhandled exception.
Element.prototype.scrollTo = vi.fn();

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
