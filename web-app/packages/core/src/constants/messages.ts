/**
 * Curated user-facing copy.
 *
 * SECURITY: error toasts map an HTTP status to a string from this file. Never
 * surface ApiError.message or ApiError.body — server payloads can carry stack
 * traces and internal route names.
 */
export const messages = {
  toasts: {
    sessionExpired: "Session expired. Please sign in again.",
    forbidden: "You don't have permission to do this.",
    notFound: "Resource not found.",
    conflictError: "This conflicts with the current state.",
    validationError: "Invalid data.",
    genericError: "Something went wrong. Please try again.",
  },
} as const
