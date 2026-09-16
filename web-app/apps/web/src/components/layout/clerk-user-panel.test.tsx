import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { SidebarProvider } from "@app/ui"
import { ClerkUserPanel } from "./clerk-user-panel"

// ClerkUserPanel is a pure adapter: it maps Clerk's user object onto
// UserDetailsPanel's shape. The test mocks the SDK and asserts on the mapping —
// testing the adapter, not Clerk.
const { useAppAuth, signOut, openUserProfile } = vi.hoisted(() => ({
  useAppAuth: vi.fn(),
  signOut: vi.fn(),
  openUserProfile: vi.fn(),
}))

vi.mock("@app/auth", () => ({ useAppAuth }))
vi.mock("@clerk/nextjs", () => ({
  useClerk: () => ({ signOut, openUserProfile }),
}))

// UserDetailsPanel calls useSidebar(). See nav-sidebar.test.tsx on the wrapper.
function renderInSidebar(ui: ReactNode) {
  return render(<SidebarProvider>{ui}</SidebarProvider>)
}

function clerkUser(overrides: Record<string, unknown> = {}) {
  return {
    firstName: "Ada",
    lastName: "Lovelace",
    imageUrl: "https://img.test/a.png",
    primaryEmailAddress: { emailAddress: "ada@test.dev" },
    ...overrides,
  }
}

beforeEach(() => {
  useAppAuth.mockReset()
})

describe("ClerkUserPanel", () => {
  it("maps a loaded user onto the panel", () => {
    useAppAuth.mockReturnValue({ isLoaded: true, user: clerkUser() })
    renderInSidebar(<ClerkUserPanel />)

    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument()
    expect(screen.getByText("ada@test.dev")).toBeInTheDocument()
  })

  it("falls back to 'User' when the name is empty", () => {
    // Both name fields are optional in Clerk, and join("") on two nulls yields
    // "", which would render an empty row rather than anything meaningful.
    useAppAuth.mockReturnValue({
      isLoaded: true,
      user: clerkUser({ firstName: null, lastName: null }),
    })
    renderInSidebar(<ClerkUserPanel />)

    expect(screen.getByText("User")).toBeInTheDocument()
  })

  it("uses whichever name part exists", () => {
    useAppAuth.mockReturnValue({
      isLoaded: true,
      user: clerkUser({ lastName: null }),
    })
    renderInSidebar(<ClerkUserPanel />)

    expect(screen.getByText("Ada")).toBeInTheDocument()
  })

  it("falls back when there is no primary email", () => {
    useAppAuth.mockReturnValue({
      isLoaded: true,
      user: clerkUser({ primaryEmailAddress: null }),
    })
    renderInSidebar(<ClerkUserPanel />)

    expect(screen.getByText("No email")).toBeInTheDocument()
  })

  it("passes null while auth is still loading, so the panel skeletons", () => {
    // Never render null for a loading state — the panel shows skeletons, and
    // passing user={null} is what triggers them.
    useAppAuth.mockReturnValue({ isLoaded: false, user: null })
    renderInSidebar(<ClerkUserPanel />)

    expect(screen.queryByText("Ada Lovelace")).not.toBeInTheDocument()
    expect(document.querySelector('[data-slot="skeleton"]')).not.toBeNull()
  })

  it("passes null when loaded but signed out", () => {
    useAppAuth.mockReturnValue({ isLoaded: true, user: null })
    renderInSidebar(<ClerkUserPanel />)

    expect(document.querySelector('[data-slot="skeleton"]')).not.toBeNull()
  })
})
