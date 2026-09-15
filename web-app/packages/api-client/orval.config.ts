import { defineConfig } from "orval"

// Both targets read the same committed artifact. Routes tagged "streaming" are
// SSE: they have no JSON response schema, and generating a react-query mutation
// for one produces a misleading `unknown`-returning hook nobody should call.
const input = {
  target: "../../../server/openapi.json",
  filters: { mode: "exclude" as const, tags: ["streaming"] },
}

export default defineConfig({
  appApi: {
    input,
    output: {
      mode: "tags-split",
      target: "./src/generated/endpoints",
      schemas: "./src/generated/types",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      // orval 8.x names this `formatter`; the older `prettier: true` is not a
      // valid OutputOptions key and is silently ignored, leaving it unformatted.
      formatter: "prettier",
      override: {
        // Without this, the generated types describe an { data, status, headers }
        // envelope while the mutator resolves the parsed body — a disagreement
        // that forces `as unknown as T` at every call site.
        fetch: { includeHttpResponseReturnType: false },
        // A `use`-prefixed mutator name makes orval call it inside each hook,
        // which is what removes the need for a module-level client singleton.
        mutator: {
          path: "./src/use-api-fetch.ts",
          name: "useApiFetch",
        },
        // Deliberately no `query.useQuery` / `query.useMutation` here. Those are
        // global forces, not "generate both kinds": orval resolves them as
        //   effectiveUseQuery    = override.query.useQuery    ?? verb === GET
        //   effectiveUseMutation = override.query.useMutation ?? verb !== GET
        // and then breaks the tie with `if (GET && isMutation) isQuery = false`
        // and `if (!GET && isQuery) isMutation = false`. Setting both to true
        // therefore inverts every operation — GET /ready becomes a mutation, and
        // DELETE /auth/me becomes a useQuery that fires on mount and refetches on
        // window focus. Omitting them lets orval key off the verb, which is what
        // we want: queries for GET, mutations for everything else.
      },
    },
  },
  appZod: {
    input,
    output: {
      mode: "tags-split",
      target: "./src/generated/zod",
      client: "zod",
      clean: true,
      formatter: "prettier", // see appApi above
    },
  },
})
