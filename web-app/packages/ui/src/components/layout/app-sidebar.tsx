"use client"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarFooterMenu,
  SidebarGroup,
  SidebarHeader,
  SidebarMenuItem,
} from "../ui/sidebar"
import { MenuNavigator } from "./nav-sidebar"
import { CompanyLogo } from "./company-logo"
import type { NavItem } from "../../types/nav"

interface AppSidebarProps extends React.ComponentProps<typeof Sidebar> {
  items: NavItem[]
  logoSrc: string
  logoAlt?: string
  settingsSlot?: React.ReactNode
  userSlot?: React.ReactNode
}

export function AppSidebar({
  items,
  logoSrc,
  logoAlt,
  settingsSlot,
  userSlot,
  ...props
}: AppSidebarProps) {
  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <CompanyLogo src={logoSrc} alt={logoAlt} />
      </SidebarHeader>
      <SidebarContent>
        <MenuNavigator items={items} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarGroup>
          <SidebarFooterMenu>
            {settingsSlot && <SidebarMenuItem>{settingsSlot}</SidebarMenuItem>}
            {userSlot}
          </SidebarFooterMenu>
        </SidebarGroup>
      </SidebarFooter>
    </Sidebar>
  )
}
