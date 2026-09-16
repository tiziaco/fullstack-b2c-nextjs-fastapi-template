import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { SidebarProvider } from "@app/ui"
import type { NavItem } from "@app/core/types/nav"
import { MenuNavigator } from "./nav-sidebar"

// usePathname is the component's only input besides its props. Mocking the
// module (rather than wrapping in a real router) is the pattern a fork copies
// for every other route-aware component.
const { usePathname } = vi.hoisted(() => ({ usePathname: vi.fn() }))

vi.mock("next/navigation", () => ({ usePathname }))

// SidebarMenuButton calls useSidebar(), which throws outside a provider, and
// MenuNavigator renders one in both of its branches. SidebarProvider in turn
// calls useIsMobile() -> window.matchMedia, stubbed in vitest.setup.ts.
//
// Inlined rather than shared: a helper would need a cross-package import or a
// path alias in six standalone tsconfigs. Promote it to an @app/test-utils
// package once a third test file needs it.
function renderInSidebar(ui: ReactNode) {
  return render(<SidebarProvider>{ui}</SidebarProvider>)
}

const FLAT: NavItem[] = [
  { title: "Home", url: "/home" },
  { title: "Reports", url: "/reports" },
]

describe("MenuNavigator", () => {
  it("marks the item matching the current path", () => {
    usePathname.mockReturnValue("/home")
    renderInSidebar(<MenuNavigator items={FLAT} />)

    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute(
      "aria-current",
      "page",
    )
    expect(screen.getByRole("link", { name: "Reports" })).not.toHaveAttribute(
      "aria-current",
    )
  })

  it("matches the path exactly, so a child route does not light up its parent", () => {
    // This pins a decision rather than an accident: /home/settings leaves /home
    // inactive because the check is `pathname === item.url`, not startsWith.
    // Changing to prefix matching should fail here and be a deliberate choice.
    usePathname.mockReturnValue("/home/settings")
    renderInSidebar(<MenuNavigator items={FLAT} />)

    expect(screen.getByRole("link", { name: "Home" })).not.toHaveAttribute(
      "aria-current",
    )
  })

  it("falls back to / when usePathname returns null", () => {
    usePathname.mockReturnValue(null)
    renderInSidebar(<MenuNavigator items={FLAT} />)

    expect(screen.getByRole("link", { name: "Home" })).not.toHaveAttribute(
      "aria-current",
    )
  })

  it("renders the icon when one is supplied", () => {
    usePathname.mockReturnValue("/home")
    const Icon = () => <svg data-testid="nav-icon" />
    renderInSidebar(<MenuNavigator items={[{ ...FLAT[0], icon: Icon }]} />)

    expect(screen.getByTestId("nav-icon")).toBeInTheDocument()
  })
})

describe("MenuNavigator, collapsible branch", () => {
  const NESTED: NavItem[] = [
    {
      title: "Home",
      url: "/home",
      items: [{ title: "Sub A", url: "/home/a" }],
    },
  ]

  it("still marks the top-level item active", () => {
    usePathname.mockReturnValue("/home")
    renderInSidebar(<MenuNavigator items={NESTED} />)

    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute(
      "aria-current",
      "page",
    )
  })

  // Documents current behaviour, which is a bug rather than a design choice.
  // See web-app/docs/bugs.md, "Sidebar nav sub-items never render".
  //
  // <Collapsible> is rendered with no `defaultOpen`, and nothing anywhere in
  // the app renders a <CollapsibleTrigger> — it is exported from @app/ui but
  // never used. CollapsibleContent is Base UI's Panel, whose `keepMounted`
  // defaults to false, so a closed panel is not in the DOM and there is no
  // control that could open it.
  //
  // Nobody has noticed because HUB_NAV (apps/web/src/lib/hub-nav.ts) has a
  // single flat entry, so this branch never runs in the app. When the branch is
  // fixed, this test should fail — invert it, do not delete it.
  it("does not render sub-items: the panel is closed and has no trigger", () => {
    usePathname.mockReturnValue("/home")
    renderInSidebar(<MenuNavigator items={NESTED} />)

    expect(screen.queryByText("Sub A")).not.toBeInTheDocument()
    expect(screen.queryAllByRole("link")).toHaveLength(1)
  })
})
