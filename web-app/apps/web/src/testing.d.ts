// Makes jest-dom's matchers (toBeInTheDocument, toHaveAttribute, ...) visible to
// tsc in this package.
//
// vitest.setup.ts imports the same module at runtime, but that file belongs to
// no package's tsconfig `include`, so its type augmentation does not reach here.
// Each package with component tests needs its own copy. A `types` array in the
// tsconfig would be the alternative, but there is no shared base config to put
// it in and on apps/web it would shadow the ambient Next types.
import "@testing-library/jest-dom/vitest"
