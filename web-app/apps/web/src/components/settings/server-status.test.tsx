import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { ServerHealthIndicator } from "./server-status"

const { useServerStatus, env } = vi.hoisted(() => ({
  useServerStatus: vi.fn(),
  env: { isDevelopment: false },
}))

vi.mock("@/hooks/use-server-status", () => ({ useServerStatus }))

// isDevelopment is computed ONCE at module load from process.env.NODE_ENV
// (apps/web/src/lib/env-helpers.ts). Vitest sets NODE_ENV=test, so the real
// value is always false and the entire HoverCard branch would silently never
// render — a naive test passes while covering half the component. Reassigning
// process.env.NODE_ENV mid-test does nothing; the module has to be mocked, and
// a getter is what lets one file exercise both sides of the branch.
vi.mock("@/lib/env-helpers", () => ({
  get isDevelopment() {
    return env.isDevelopment
  },
  get isProduction() {
    return !env.isDevelopment
  },
  get isTest() {
    return false
  },
}))

function readiness(status: "healthy" | "degraded") {
  return {
    components: {
      agents: { chatbot: { graph_compiled: true, ready: true } },
      agents_healthy: true,
      api: "healthy" as const,
      database: {
        connection_pool: {
          checked_in: 1,
          checked_out: 0,
          overflow: 0,
          size: 5,
          total: 5,
        },
        status: "healthy" as const,
      },
    },
    environment: "development" as const,
    status,
    timestamp: "2026-09-16T12:00:00+00:00",
    version: "1.2.3",
  }
}

/** The status dot carries its state in a Tailwind colour class, not a role. */
function dotClasses() {
  const dot = document.querySelector("div.size-2.rounded-full")
  return dot?.className ?? ""
}

beforeEach(() => {
  env.isDevelopment = false
  useServerStatus.mockReset()
  useServerStatus.mockReturnValue({
    status: readiness("healthy"),
    isLoading: false,
    error: undefined,
  })
})

describe("ServerHealthIndicator", () => {
  it("shows a loading placeholder before the first result", () => {
    useServerStatus.mockReturnValue({ isLoading: true })
    render(<ServerHealthIndicator />)

    expect(screen.getByText("Loading...")).toBeInTheDocument()
  })

  it("is green and pinging when healthy", () => {
    render(<ServerHealthIndicator />)

    expect(dotClasses()).toContain("bg-green-500")
    expect(document.querySelector(".animate-ping")).not.toBeNull()
    expect(screen.getByText("v1.2.3")).toBeInTheDocument()
  })

  it("is yellow and not pinging when degraded", () => {
    useServerStatus.mockReturnValue({
      status: readiness("degraded"),
      isLoading: false,
      error: undefined,
    })
    render(<ServerHealthIndicator />)

    expect(dotClasses()).toContain("bg-yellow-500")
    expect(document.querySelector(".animate-ping")).toBeNull()
  })

  it("is red when there is no status at all", () => {
    useServerStatus.mockReturnValue({ isLoading: false })
    render(<ServerHealthIndicator />)

    expect(dotClasses()).toContain("bg-red-500")
    expect(screen.getByText("v0.0.0")).toBeInTheDocument()
  })

  it("is red when an error is present even though a payload is", () => {
    // The colour chain tests `error || !status` FIRST. This is the half of the
    // contract that useServerStatus documents from the other side: it must
    // clear the error when it recovers a degraded body, or the indicator stays
    // red regardless of what it recovered.
    useServerStatus.mockReturnValue({
      status: readiness("healthy"),
      isLoading: false,
      error: new Error("boom"),
    })
    render(<ServerHealthIndicator />)

    expect(dotClasses()).toContain("bg-red-500")
  })
})

describe("ServerHealthIndicator, development detail", () => {
  it("renders no hover card outside development", () => {
    render(<ServerHealthIndicator />)

    expect(
      document.querySelector('[data-slot="hover-card-trigger"]'),
    ).toBeNull()
  })

  it("wraps the indicator in a hover card in development", () => {
    env.isDevelopment = true
    render(<ServerHealthIndicator />)

    expect(
      document.querySelector('[data-slot="hover-card-trigger"]'),
    ).not.toBeNull()
  })
})
