"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Collapsible, CollapsibleContent } from "../../primitives/collapsible"
import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "../../primitives/sidebar"
import type { NavItem } from "@app/core/types/nav"

export function MenuNavigator({ items }: { items: NavItem[] }) {
  const pathname = usePathname() || "/"

  return (
    <SidebarGroup>
      <SidebarMenu>
        {items.map((item) => {
          const isActive = pathname === item.url
          const hasItems = item.items && item.items.length > 0

          if (hasItems) {
            return (
              <Collapsible key={item.title} className="group/collapsible">
                <SidebarMenuItem>
                  <div className="relative flex items-center w-full">
                    <SidebarMenuButton
                      size="lg"
                      tooltip={item.title}
                      isActive={isActive}
                    >
                      <Link
                        href={item.url}
                        className={`flex items-center gap-2 w-full ${isActive ? "font-medium" : ""}`}
                        aria-current={isActive ? "page" : undefined}
                      >
                        {item.icon && <item.icon />}
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </div>
                  {item.items?.length ? (
                    <CollapsibleContent>
                      <SidebarMenuSub>
                        {item.items.map((subItem) => {
                          const isSubActive = pathname === subItem.url
                          return (
                            <SidebarMenuSubItem key={subItem.title}>
                              <SidebarMenuSubButton isActive={isSubActive}>
                                <Link href={subItem.url}>{subItem.title}</Link>
                              </SidebarMenuSubButton>
                            </SidebarMenuSubItem>
                          )
                        })}
                      </SidebarMenuSub>
                    </CollapsibleContent>
                  ) : null}
                </SidebarMenuItem>
              </Collapsible>
            )
          }

          return (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton
                size="lg"
                tooltip={item.title}
                isActive={isActive}
              >
                <Link
                  href={item.url}
                  className={`flex items-center gap-2 w-full ${isActive ? "font-medium" : ""}`}
                  aria-current={isActive ? "page" : undefined}
                >
                  {item.icon && <item.icon />}
                  <span>{item.title}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )
        })}
      </SidebarMenu>
    </SidebarGroup>
  )
}
