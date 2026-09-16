import { AppSidebar } from "@app/components/layout/app-sidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarMenuButton,
  SidebarTrigger,
} from "@app/ui/sidebar"
import { HUB_NAV } from "@/lib/hub-nav"
import {
  SettingsDialog,
  type SettingsTab,
} from "@/components/settings/settings-dialog"
import { GeneralSettings } from "@/components/settings/general-settings"
import { ClerkUserPanel } from "@/components/layout/clerk-user-panel"
import { Settings, Cog } from "lucide-react"

const SETTINGS_TABS: SettingsTab[] = [
  {
    id: "general",
    label: "General",
    icon: <Settings className="w-5 h-5" />,
    content: <GeneralSettings />,
  },
]

export default function HubLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <AppSidebar
        items={HUB_NAV}
        logoSrc="/images/logo-small.png"
        logoAlt="Template App"
        variant="floating"
        settingsSlot={
          <SettingsDialog
            tabs={SETTINGS_TABS}
            trigger={
              <SidebarMenuButton
                size="lg"
                tooltip="Settings"
                className="cursor-pointer"
              >
                <Cog />
                <span>Settings</span>
              </SidebarMenuButton>
            }
          />
        }
        userSlot={<ClerkUserPanel />}
      />
      <SidebarTrigger
        size="icon"
        className="text-muted-foreground hover:text-foreground hover:bg-transparent cursor-pointer"
      />
      <SidebarInset className="flex flex-col overflow-hidden">
        <div className="flex-1 overflow-auto">
          <div className="px-4 py-4 min-w-0">{children}</div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
