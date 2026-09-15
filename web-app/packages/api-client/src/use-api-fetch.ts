"use client"

import { useCallback } from "react"
import { useAppAuth } from "@app/auth"

import { ApiError } from "./errors"

/**
 * The error type orval wires into every generated hook's `TError`.
 *
 * orval looks for the literal text `export type ErrorType` in this file and,
 * finding it, emits `ErrorType<...>` in place of the error type it would
 * otherwise derive from the spec's declared error response. Without it every
 * hook advertises an error it cannot produce — `useGetMe().error` typed as
 * HTTPValidationError, `useGetReadiness().error` as ReadinessResponse — while
 * the mutator below only ever throws ApiError.
 *
 * The body parameter is accepted and deliberately ignored. Nothing validates
 * the payload against the declared error schema, so `ApiError.body` stays
 * `unknown`: narrowing it here would relocate the lie rather than remove it.
 */
export type ErrorType<_Body = unknown> = ApiError

function resolveBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL
  if (!url) {
    throw new Error("@app/api-client: NEXT_PUBLIC_API_URL is not set")
  }
  // Generated routes always start with "/", so a configured value ending in one
  // would produce "//api/v1/...", which presents as a confusing 404.
  return url.replace(/\/+$/, "")
}

async function parseErrorBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? ""
  try {
    if (contentType.includes("application/json")) return await response.json()
    return await response.text()
  } catch {
    return null
  }
}

/**
 * The mutator every generated endpoint routes through.
 *
 * It is a hook, not a module-level singleton, and that is deliberate. A
 * module-scope client would be shared across concurrent requests in a Next.js
 * server process — one user's token serving another user's request — and
 * would freeze the first render's getToken closure. As a hook it reads the
 * current token on every call, needs no provider of its own, and makes the
 * provider ordering in the root layout irrelevant.
 *
 * orval recognises the `use` prefix and calls this inside each generated hook.
 */
export function useApiFetch() {
  const { getToken } = useAppAuth()

  return useCallback(
    async <T>(url: string, init?: RequestInit): Promise<T> => {
      const fullUrl = /^https?:\/\//i.test(url)
        ? url
        : `${resolveBaseUrl()}${url}`
      const headers = new Headers(init?.headers)

      const token = await getToken()
      if (token && !headers.has("authorization")) {
        headers.set("Authorization", `Bearer ${token}`)
      }

      // Only set a JSON content type for plain bodies. Never for FormData — the
      // browser must set its own multipart boundary — nor for Blob or ArrayBuffer.
      const body = init?.body
      if (
        body != null &&
        !headers.has("content-type") &&
        !(body instanceof FormData) &&
        !(body instanceof Blob) &&
        !(body instanceof ArrayBuffer)
      ) {
        headers.set("Content-Type", "application/json")
      }

      const response = await fetch(fullUrl, { ...init, headers })
      const requestId = response.headers.get("x-request-id")

      if (!response.ok) {
        // Deliberately not response.statusText: the reason phrase is server-supplied
        // text, and server error text must never reach the UI. status, body and
        // requestId still carry everything needed to debug.
        throw new ApiError(
          `HTTP ${response.status}`,
          response.status,
          await parseErrorBody(response),
          requestId,
        )
      }

      if (response.status === 204) return undefined as T
      if (response.headers.get("content-length") === "0") return undefined as T

      const contentType = response.headers.get("content-type") ?? ""
      if (contentType.includes("application/json"))
        return (await response.json()) as T

      return (await response.text()) as unknown as T
    },
    [getToken],
  )
}
