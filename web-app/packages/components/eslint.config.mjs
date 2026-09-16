import { defineConfig, globalIgnores } from "eslint/config"
import nextVitals from "eslint-config-next/core-web-vitals"
import nextTs from "eslint-config-next/typescript"

// Same rules as the portals. This package is a library, not a Next app, so the
// rule that looks for a pages/ directory is switched off.
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  { rules: { "@next/next/no-html-link-for-pages": "off" } },
  globalIgnores(["dist/**", "build/**"]),
])

export default eslintConfig
