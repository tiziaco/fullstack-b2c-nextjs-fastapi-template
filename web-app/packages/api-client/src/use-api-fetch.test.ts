import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"
import { ApiError } from "./errors"
import { useApiFetch } from "./use-api-fetch"

// useApiFetch is a hook so it can read a fresh Clerk token per call. Only the
// token source is mocked; everything else here is the real mutator.
const { getToken } = vi.hoisted(() => ({ getToken: vi.fn() }))

vi.mock("@app/auth", () => ({ useAppAuth: () => ({ getToken }) }))

function jsonResponse(
  body: unknown,
  init: { status?: number; headers?: Record<string, string> } = {},
) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "content-type": "application/json", ...init.headers },
  })
}

/** The last RequestInit that reached fetch, for asserting on headers. */
function lastCall() {
  const mock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
  const [url, init] = mock.mock.calls.at(-1) as [string, RequestInit]
  return { url, headers: new Headers(init.headers) }
}

function callApi() {
  return renderHook(() => useApiFetch()).result.current
}

/**
 * Await a call expected to reject and hand back the ApiError.
 *
 * `.catch((e) => e)` would type the result as `unknown` and fail `tsc --noEmit`
 * — test files are type-checked by the workspace type-check, same as source.
 */
async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (caught) {
    expect(caught).toBeInstanceOf(ApiError)
    return caught as ApiError
  }
  throw new Error("expected the request to reject, but it resolved")
}

beforeEach(() => {
  getToken.mockReset()
  getToken.mockResolvedValue("tok-123")
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ok: true })))
  process.env.NEXT_PUBLIC_API_URL = "http://localhost:8100"
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("base URL resolution", () => {
  it("prefixes a generated route with the configured base", async () => {
    await callApi()("/api/v1/me")
    expect(lastCall().url).toBe("http://localhost:8100/api/v1/me")
  })

  it("strips trailing slashes so routes do not double up", async () => {
    // A configured value ending in "/" would produce "//api/v1/...", which
    // presents as a confusing 404 rather than a config error.
    process.env.NEXT_PUBLIC_API_URL = "http://localhost:8100///"
    await callApi()("/api/v1/me")
    expect(lastCall().url).toBe("http://localhost:8100/api/v1/me")
  })

  it("passes an absolute URL through untouched", async () => {
    await callApi()("https://example.test/thing")
    expect(lastCall().url).toBe("https://example.test/thing")
  })

  it("throws a named error when the base URL is unset", async () => {
    delete process.env.NEXT_PUBLIC_API_URL
    await expect(callApi()("/api/v1/me")).rejects.toThrow(
      "@app/api-client: NEXT_PUBLIC_API_URL is not set",
    )
  })
})

describe("authorization header", () => {
  it("attaches the current token", async () => {
    await callApi()("/api/v1/me")
    expect(lastCall().headers.get("authorization")).toBe("Bearer tok-123")
  })

  it("omits the header when there is no token", async () => {
    getToken.mockResolvedValue(null)
    await callApi()("/api/v1/me")
    expect(lastCall().headers.has("authorization")).toBe(false)
  })

  it("does not overwrite a caller-supplied header", async () => {
    await callApi()("/api/v1/me", {
      headers: { Authorization: "Bearer caller" },
    })
    expect(lastCall().headers.get("authorization")).toBe("Bearer caller")
  })
})

describe("content type", () => {
  it("sets JSON for a plain body", async () => {
    await callApi()("/api/v1/me", {
      method: "POST",
      body: JSON.stringify({ a: 1 }),
    })
    expect(lastCall().headers.get("content-type")).toBe("application/json")
  })

  it("leaves FormData alone so the browser sets its own boundary", async () => {
    await callApi()("/api/v1/upload", {
      method: "POST",
      body: new FormData(),
    })
    expect(lastCall().headers.has("content-type")).toBe(false)
  })

  it("leaves Blob alone", async () => {
    await callApi()("/api/v1/upload", {
      method: "POST",
      body: new Blob(["x"]),
    })
    expect(lastCall().headers.has("content-type")).toBe(false)
  })

  it("sets nothing when there is no body", async () => {
    await callApi()("/api/v1/me")
    expect(lastCall().headers.has("content-type")).toBe(false)
  })
})

describe("responses", () => {
  it("parses a JSON body", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse({ id: 7 }))
    await expect(callApi()("/api/v1/me")).resolves.toEqual({ id: 7 })
  })

  it("returns undefined for 204", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(null, { status: 204 }),
    )
    await expect(callApi()("/api/v1/thing")).resolves.toBeUndefined()
  })

  it("returns undefined when content-length is 0", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response("", { status: 200, headers: { "content-length": "0" } }),
    )
    await expect(callApi()("/api/v1/thing")).resolves.toBeUndefined()
  })

  it("returns text for a non-JSON content type", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response("plain", {
        status: 200,
        headers: { "content-type": "text/plain" },
      }),
    )
    await expect(callApi()("/api/v1/thing")).resolves.toBe("plain")
  })
})

describe("errors", () => {
  it("throws ApiError carrying status, parsed body and request id", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      jsonResponse(
        { detail: "nope" },
        { status: 403, headers: { "x-request-id": "req-abc" } },
      ),
    )

    const error = await rejection(callApi()("/api/v1/me"))

    expect(error.status).toBe(403)
    expect(error.body).toEqual({ detail: "nope" })
    expect(error.requestId).toBe("req-abc")
  })

  it("uses the status as the message, never the server's reason phrase", async () => {
    // Server-authored text must never reach the UI. QueryProvider maps status
    // to curated copy; a leaked reason phrase would bypass that entirely.
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response("{}", { status: 500, statusText: "Internal Kaboom" }),
    )

    const error = await rejection(callApi()("/api/v1/me"))

    expect(error.message).toBe("HTTP 500")
    expect(error.message).not.toContain("Kaboom")
  })

  it("keeps a 503 body intact so callers can recover it", async () => {
    // useServerStatus depends on exactly this: the degraded readiness payload
    // arrives as ApiError.body, never as data.
    vi.mocked(globalThis.fetch).mockResolvedValue(
      jsonResponse({ status: "degraded" }, { status: 503 }),
    )

    const error = await rejection(callApi()("/api/v1/ready"))

    expect(error.body).toEqual({ status: "degraded" })
  })

  it("survives an unparseable error body", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response("<html>gateway</html>", {
        status: 502,
        headers: { "content-type": "application/json" },
      }),
    )

    const error = await rejection(callApi()("/api/v1/me"))

    expect(error.body).toBeNull()
    expect(error.requestId).toBeNull()
  })
})
