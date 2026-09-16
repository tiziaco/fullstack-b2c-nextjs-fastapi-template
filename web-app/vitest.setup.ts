import { afterEach } from "vitest"
import { cleanup } from "@testing-library/react"
import "@testing-library/jest-dom/vitest"

// Testing Library auto-cleans only when `globals: true`. This config runs with
// globals off, so without this every test leaks its DOM into the next one and
// the failure surfaces as a duplicate-match error far from its cause.
afterEach(() => {
  cleanup()
})

// jsdom does not implement matchMedia, and useIsMobile (packages/ui/src/hooks/
// use-mobile.ts) calls it. SidebarProvider uses that hook, so every test that
// renders MenuNavigator, SettingsDialog or anything else inside a sidebar dies
// here before reaching an assertion. This stub is the reason a setup file exists.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
    // Deprecated, but Base UI and other libraries still feature-detect them.
    addListener: () => {},
    removeListener: () => {},
  }),
})

// resolveBaseUrl() in packages/api-client/src/use-api-fetch.ts throws when this
// is unset. Next inlines it at build time; under Vitest it is a plain runtime
// read, so it has to be given a value. Tests that exercise the unset branch
// delete it themselves.
process.env.NEXT_PUBLIC_API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8100"
