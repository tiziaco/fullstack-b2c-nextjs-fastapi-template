import { fileURLToPath } from "node:url"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

// Force the test environment before anything reads it.
//
// Vitest only defaults NODE_ENV to "test" when it is UNSET, so any caller that
// exports NODE_ENV silently decides how React builds. When it is "production",
// React loads its production build, Testing Library falls back to the
// deprecated act path, and every render test fails with an error that points
// nowhere near the cause.
//
// This is defence, not a workaround for a known bug: the one source that used
// to set it — NODE_ENV=production in apps/web/.env.example, re-exported by the
// root Makefile's `-include` — has been removed. Keep this line anyway. It is
// one statement, it covers every entry point (`pnpm test`, `make test-web`, an
// editor's runner, CI), and the failure it prevents is expensive to diagnose.
process.env.NODE_ENV = "test"

// One config for the whole workspace. Tests are co-located with their subjects,
// so there is no glob to maintain — see web-app/CLAUDE.md for why this diverges
// from server/tests/.
//
// A single config works even though tests live in five packages: Vite resolves
// `@app/*` through each package's `exports` field and pnpm's workspace symlinks,
// exactly as Next does via `transpilePackages`. Nothing here is built, so there
// is no artifact to resolve against and none is needed.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // `@/` means apps/web/src and nowhere else. packages/ui declares the same
      // alias in its tsconfig but never uses it, so there is no collision — if
      // that ever changes, this config has to split into test.projects.
      "@/": `${fileURLToPath(new URL("./apps/web/src", import.meta.url))}/`,
    },
    // Every package has its own `react` symlink. They all point at the same
    // physical copy today because apps/web pins an exact version, but a drift to
    // two copies would surface as "invalid hook call" from inside a primitive,
    // which is a miserable thing to debug. Pin the resolution instead.
    dedupe: ["react", "react-dom"],
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    // Vitest's default include matches BOTH `.test.` and `.spec.`. Playwright
    // specs land in e2e/ later and must never be run by this runner — they need
    // a live stack — so the split is pinned here rather than left to a
    // directory exclusion: `.test.` is Vitest, `.spec.` is Playwright.
    include: ["**/*.test.?(c|m)[jt]s?(x)"],
    exclude: ["**/node_modules/**", "**/.next/**", "**/dist/**", "e2e/**"],
    // Explicit imports from "vitest" instead of globals. Globals would need a
    // `types` array in six standalone tsconfigs (there is no shared base and no
    // `extends` anywhere), and on apps/web a `types` array shadows the ambient
    // Next types.
    globals: false,
  },
})
