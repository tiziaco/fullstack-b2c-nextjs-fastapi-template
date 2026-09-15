/**
 * The single error type the application layer needs to know about.
 *
 * `requestId` is the server's correlation id, read from X-Request-ID.
 * CorrelationIdMiddleware stamps every request and binds the id to the
 * server's structured logs, so a client-side failure is traceable to a
 * server log line.
 */
export class ApiError extends Error {
  readonly status: number
  readonly body: unknown
  readonly requestId: string | null

  constructor(
    message: string,
    status: number,
    body: unknown,
    requestId: string | null,
  ) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.body = body
    this.requestId = requestId
  }
}
