import { describe, expect, it } from "vitest"
import { ROLE_LABELS, Role, getUserRole, isAdmin } from "./permissions"

// getUserRole is the portability seam: the only function that knows how the
// auth provider represents a role. These cases are the contract a provider
// migration has to keep.
describe("getUserRole", () => {
  it("narrows a recognised claim to a Role", () => {
    expect(getUserRole("user")).toBe(Role.USER)
    expect(getUserRole("admin")).toBe(Role.ADMIN)
  })

  it("returns null for an unrecognised claim", () => {
    // The point of the seam: an unknown value must never be treated as a role.
    expect(getUserRole("hacker")).toBeNull()
    expect(getUserRole("org:admin")).toBeNull()
    expect(getUserRole("Admin")).toBeNull()
  })

  it("returns null for an absent claim", () => {
    expect(getUserRole(null)).toBeNull()
    expect(getUserRole(undefined)).toBeNull()
    expect(getUserRole("")).toBeNull()
  })
})

describe("isAdmin", () => {
  it("is true only for the admin role", () => {
    expect(isAdmin(Role.ADMIN)).toBe(true)
    expect(isAdmin(Role.USER)).toBe(false)
    expect(isAdmin(null)).toBe(false)
  })
})

describe("ROLE_LABELS", () => {
  it("covers every role", () => {
    // Record<Role, string> makes this a type error to get wrong, but the test
    // also catches a label silently emptied.
    for (const role of Object.values(Role)) {
      expect(ROLE_LABELS[role]).toBeTruthy()
    }
  })
})
