#!/usr/bin/env node
/**
 * Regenerate the barrel index.ts files under src/generated/.
 *
 * orval's `clean: true` wipes its target directories on every run, so the
 * barrels must be rewritten afterwards. Invoked by the `gen:api` script.
 *
 * - endpoints/ and zod/ use the tags-split layout: one directory per OpenAPI
 *   tag, each holding <tag>.ts. Each tag gets its own index.ts — that is what
 *   the package's "./endpoints/*" and "./zod/*" subpath exports resolve to —
 *   plus one top-level barrel over all tags.
 * - types/ is flat: one .ts per schema, with a single barrel over all of them.
 *
 * One Node file rather than a shell script, because this repository is a
 * template meant to be forked and cloned onto machines without bash.
 */
import { existsSync, readdirSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const packageRoot = join(dirname(fileURLToPath(import.meta.url)), "..")
const generated = join(packageRoot, "src", "generated")

let written = 0

for (const area of ["endpoints", "zod"]) {
  const dir = join(generated, area)
  if (!existsSync(dir)) continue

  const tags = readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort()

  for (const tag of tags) {
    writeFileSync(join(dir, tag, "index.ts"), `export * from "./${tag}"\n`)
    written++
  }

  writeFileSync(
    join(dir, "index.ts"),
    tags.map((t) => `export * from "./${t}/${t}"\n`).join(""),
  )
  written++
}

const typesDir = join(generated, "types")
if (existsSync(typesDir)) {
  const modules = readdirSync(typesDir)
    .filter((file) => file.endsWith(".ts") && file !== "index.ts")
    .map((file) => file.slice(0, -3))
    .sort()

  writeFileSync(
    join(typesDir, "index.ts"),
    modules.map((m) => `export * from "./${m}"\n`).join(""),
  )
  written++
}

// A silent no-op is worse than a failure here: both loops above skip missing
// directories, so a failed generation or a filter that matched everything would
// otherwise leave this script printing success over an empty package — and a CI
// drift guard built on `gen:api` would report green on a broken tree.
if (written === 0) {
  console.error(
    `postgen: wrote no barrel files. Expected generated output under ${generated}.\n` +
      "Either orval did not run, or every operation was filtered out of both targets.",
  )
  process.exit(1)
}

console.log(`postgen: wrote ${written} barrel file(s)`)
