import { beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"
import { ApiError } from "@app/api-client"
import { useServerStatus } from "./use-server-status"

// Only the generated hook is mocked. ApiError and the generated Zod validator
// stay real, because the behaviour under test is precisely that a 503 body
// survives `GetReadinessResponse.safeParse` — a hand-rolled stub would prove
// nothing about the actual contract.
const { useGetReadiness } = vi.hoisted(() => ({ useGetReadiness: vi.fn() }))

vi.mock("@app/api-client/endpoints/system", () => ({ useGetReadiness }))

function readiness(
  overrides: { status?: "healthy" | "degraded"; version?: string } = {},
) {
  return {
    components: {
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
    status: overrides.status ?? ("healthy" as const),
    timestamp: "2026-09-16T12:00:00+00:00",
    version: overrides.version ?? "1.2.3",
  }
}

function mockQuery(value: {
  data?: unknown
  isLoading?: boolean
  error?: unknown
}) {
  useGetReadiness.mockReturnValue({
    data: value.data,
    isLoading: value.isLoading ?? false,
    error: value.error,
  })
}

beforeEach(() => {
  useGetReadiness.mockReset()
})

describe("useServerStatus", () => {
  it("passes a successful payload straight through", () => {
    const payload = readiness()
    mockQuery({ data: payload })

    const { result } = renderHook(() => useServerStatus())

    expect(result.current.status).toEqual(payload)
    expect(result.current.error).toBeUndefined()
  })

  it("recovers the degraded payload from a 503 body and clears the error", () => {
    // /ready answers 503 when degraded and useApiFetch throws on any non-ok
    // response, so the degraded payload arrives as ApiError.body, never as data.
    // Without this recovery the widget shows a bare red dot and v0.0.0.
    const payload = readiness({ status: "degraded", version: "9.9.9" })
    mockQuery({ error: new ApiError("HTTP 503", 503, payload, "req-1") })

    const { result } = renderHook(() => useServerStatus())

    expect(result.current.status).toMatchObject({
      status: "degraded",
      version: "9.9.9",
    })
    // server-status.tsx tests `error || !status` first, so leaving the 503 in
    // place would keep the indicator red despite having the detail to show.
    expect(result.current.error).toBeUndefined()
  })

  it("keeps the error when a non-503 failure arrives", () => {
    const error = new ApiError("HTTP 500", 500, { detail: "boom" }, "req-2")
    mockQuery({ error })

    const { result } = renderHook(() => useServerStatus())

    expect(result.current.error).toBe(error)
  })

  it("keeps the error when a 503 body fails validation", () => {
    // A 503 whose body is not a readiness payload (a proxy's HTML error page,
    // say) must stay an error rather than silently becoming "no status".
    const error = new ApiError("HTTP 503", 503, { nonsense: true }, "req-3")
    mockQuery({ error })

    const { result } = renderHook(() => useServerStatus())

    expect(result.current.status).toBeUndefined()
    expect(result.current.error).toBe(error)
  })

  it("prefers the recovered body over stale cached data", () => {
    // The regression this guards: a failed refetch does not evict the last
    // successful payload from the query cache, so `data` still holds the
    // healthy response from before the outage. Reading it first would show a
    // green dot and a frozen timestamp for as long as the server stayed down.
    const stale = readiness({ status: "healthy", version: "1.0.0" })
    const degraded = readiness({ status: "degraded", version: "2.0.0" })
    mockQuery({
      data: stale,
      error: new ApiError("HTTP 503", 503, degraded, "req-4"),
    })

    const { result } = renderHook(() => useServerStatus())

    expect(result.current.status).toMatchObject({ status: "degraded" })
  })

  it("keeps stale data visible but still reports a non-503 error", () => {
    const stale = readiness()
    const error = new ApiError("HTTP 401", 401, null, "req-5")
    mockQuery({ data: stale, error })

    const { result } = renderHook(() => useServerStatus())

    expect(result.current.status).toEqual(stale)
    expect(result.current.error).toBe(error)
  })

  it("forwards the loading flag", () => {
    mockQuery({ isLoading: true })

    const { result } = renderHook(() => useServerStatus())

    expect(result.current.isLoading).toBe(true)
  })
})
