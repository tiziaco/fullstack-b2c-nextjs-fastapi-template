/**
 * The package's public runtime surface is deliberately tiny. Everything else is
 * reached through the subpath exports, so importing one tag does not pull in
 * the whole client.
 */
export { ApiError } from "./errors"
export { useApiFetch } from "./use-api-fetch"
