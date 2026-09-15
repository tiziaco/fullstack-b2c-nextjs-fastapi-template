"use client"

import { ApiError } from "@app/api-client"
import { useGetReadiness } from "@app/api-client/endpoints/system"
import { GetReadinessResponse } from "@app/api-client/zod/system"

export function useServerStatus() {
  const { data, isLoading, error } = useGetReadiness({
    query: {
      refetchInterval: 30_000,
      retry: false,
      // The widget renders "degraded" on its own. A global toast every 30
      // seconds during an outage would be noise, so this query opts out.
      meta: { silentError: true },
    },
  })

  // /ready answers 503 when degraded and useApiFetch throws on any non-ok
  // response, so the degraded payload the server just serialized arrives as
  // ApiError.body — never as `data`. Recovering it here is what lets the widget
  // show yellow with component detail instead of a bare red dot and v0.0.0.
  // ApiError.body is `unknown`, so it goes through the generated validator
  // rather than a cast.
  const degraded =
    error instanceof ApiError && error.status === 503
      ? GetReadinessResponse.safeParse(error.body).data
      : undefined

  // The recovered body wins over `data`. A failed refetch does not evict the
  // last successful one from the query cache, so during an outage `data` still
  // holds the healthy payload from before it — reading that first would show a
  // green dot and a frozen timestamp for as long as the server stayed down.
  const status = degraded ?? data

  // server-status.tsx tests `error || !status` first, so leaving the 503 in
  // place after recovering its body would keep the indicator red regardless.
  // Only a recovered body clears it: every other failure — a 500, an expired
  // token, the server gone — must stay an error even though stale `data` is
  // still there to render.
  return { status, isLoading, error: degraded ? undefined : error }
}
