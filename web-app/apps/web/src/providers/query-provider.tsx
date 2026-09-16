"use client"

import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { ReactQueryDevtools } from "@tanstack/react-query-devtools"
import { useState } from "react"
import { toast } from "sonner"
import { ApiError } from "@app/api-client"
import { isDevelopment } from "../lib/env-helpers"
import { messages } from "@app/core/constants/messages"

/**
 * Map an error to a toast.
 *
 * SECURITY: status maps to curated copy. Never surface err.message or the
 * response body — server payloads may contain stack traces or internal route
 * names.
 */
function toastForError(error: unknown): void {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 401:
        toast.error(messages.toasts.sessionExpired)
        return
      case 403:
        toast.error(messages.toasts.forbidden)
        return
      case 404:
        toast.error(messages.toasts.notFound)
        return
      case 409:
        toast.error(messages.toasts.conflictError)
        return
      case 422:
        toast.error(messages.toasts.validationError)
        return
      default:
        toast.error(messages.toasts.genericError)
        return
    }
  }
  toast.error(messages.toasts.genericError)
}

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: (error, query) => {
            // onError fires for background refetches too. A polling query that
            // fails every 30s would otherwise toast every 30s, behind data the
            // user can already see. Only a query that has never resolved
            // toasts, and a query can opt out entirely.
            if (query.meta?.silentError === true) return
            if (query.state.data !== undefined) return
            toastForError(error)
          },
        }),
        // Mutations always toast: the user just acted and is waiting for a result.
        mutationCache: new MutationCache({ onError: toastForError }),
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            gcTime: 5 * 60 * 1000,
            refetchOnWindowFocus: false,
            // Retrying a 4xx burns a request for an answer that will not change.
            retry: (failureCount, error) =>
              failureCount < 1 &&
              !(error instanceof ApiError && error.status < 500),
          },
        },
      }),
  )

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {isDevelopment && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  )
}
