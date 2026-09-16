import type { ReactNode } from "react"
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { SidebarProvider } from "@app/ui"
import { SettingsDialog, type SettingsTab } from "./settings-dialog"

// SettingsDialog renders <Sidebar> and <SidebarMenuButton>, both of which call
// useSidebar(). See nav-sidebar.test.tsx for why this wrapper is inlined rather
// than shared.
function renderInSidebar(ui: ReactNode) {
  return render(<SidebarProvider>{ui}</SidebarProvider>)
}

const TABS: SettingsTab[] = [
  {
    id: "general",
    label: "General",
    icon: <svg data-testid="icon-general" />,
    content: <p>General body</p>,
  },
  {
    id: "account",
    label: "Account",
    icon: <svg data-testid="icon-account" />,
    content: <p>Account body</p>,
  },
]

/** The dialog is closed until its trigger is clicked. */
async function open(ui: ReactNode) {
  const user = userEvent.setup()
  renderInSidebar(ui)
  await user.click(screen.getByRole("button", { name: /settings/i }))
  return user
}

describe("SettingsDialog", () => {
  it("opens on the default trigger and shows the first tab", async () => {
    // activeTab initialises to tabs[0]?.id, so General is selected with no
    // interaction at all.
    await open(<SettingsDialog tabs={TABS} />)

    expect(await screen.findByText("General body")).toBeInTheDocument()
    expect(screen.queryByText("Account body")).not.toBeInTheDocument()
  })

  it("switches content when another tab is clicked", async () => {
    const user = await open(<SettingsDialog tabs={TABS} />)

    await user.click(await screen.findByRole("button", { name: /account/i }))

    expect(await screen.findByText("Account body")).toBeInTheDocument()
    expect(screen.queryByText("General body")).not.toBeInTheDocument()
  })

  it("accepts a caller-supplied trigger", async () => {
    const user = userEvent.setup()
    renderInSidebar(
      <SettingsDialog tabs={TABS} trigger={<button>Open prefs</button>} />,
    )

    await user.click(screen.getByRole("button", { name: "Open prefs" }))

    expect(await screen.findByText("General body")).toBeInTheDocument()
  })
})

// The footer slot is the seam that let SettingsDialog move out of apps/web and
// into this package: its one hardcoded <ServerHealthIndicator /> became a prop.
// This is the pattern a fork extends, so it is the one most worth pinning.
describe("SettingsDialog footerSlot", () => {
  it("renders the slot content when provided", async () => {
    await open(
      <SettingsDialog tabs={TABS} footerSlot={<span>slot content</span>} />,
    )

    expect(await screen.findByText("slot content")).toBeInTheDocument()
  })

  it("renders no footer at all when the slot is omitted", async () => {
    await open(<SettingsDialog tabs={TABS} />)
    await screen.findByText("General body")

    expect(document.querySelector('[data-slot="sidebar-footer"]')).toBeNull()
  })
})

describe("SettingsDialog with no tabs", () => {
  it("renders an empty title instead of crashing", async () => {
    // `tabs[0]?.id ?? ""` exists for this case, which nothing in the app has
    // ever produced. tabs.find() then returns undefined and both `active?.`
    // reads fall back.
    await open(<SettingsDialog tabs={[]} />)

    const title = await screen.findByRole("heading")
    expect(title).toHaveTextContent("")
  })
})
