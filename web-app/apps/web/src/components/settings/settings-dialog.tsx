"use client"

import type React from "react"
import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogTrigger,
  DialogTitle,
} from "@app/ui/dialog"
import { Button } from "@app/ui/button"
import { Separator } from "@app/ui/separator"
import { Cog } from "lucide-react"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@app/ui/sidebar"
import { ServerHealthIndicator } from "./server-status"

export interface SettingsTab {
  id: string
  label: string
  icon: React.ReactNode
  content: React.ReactNode
}

interface SettingsDialogProps {
  tabs: SettingsTab[]
  trigger?: React.ReactElement
}

export function SettingsDialog({ tabs, trigger }: SettingsDialogProps) {
  const [activeTab, setActiveTab] = useState(tabs[0]?.id ?? "")
  const active = tabs.find((t) => t.id === activeTab)

  return (
    <Dialog>
      <DialogTrigger
        render={
          trigger ?? (
            <Button
              variant="ghost"
              size="default"
              className="w-full justify-start"
            >
              <Cog />
              <span>Settings</span>
            </Button>
          )
        }
      />
      <DialogContent className="max-w-2xl! h-125 p-0 gap-0 overflow-hidden">
        <div className="flex h-full">
          <Sidebar collapsible="none" className="w-50 border-r flex flex-col">
            <SidebarContent className="p-3 mt-10 flex-1">
              <SidebarMenu>
                {tabs.map((tab) => (
                  <SidebarMenuItem key={tab.id}>
                    <SidebarMenuButton
                      isActive={activeTab === tab.id}
                      onClick={() => setActiveTab(tab.id)}
                    >
                      {tab.icon}
                      {tab.label}
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarContent>
            <SidebarFooter>
              <ServerHealthIndicator />
            </SidebarFooter>
          </Sidebar>
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="overflow-y-auto flex-1">
              <div className="p-6 pt-3">
                <DialogTitle className="text-2xl mb-2 font-semibold capitalize">
                  {active?.label ?? ""}
                </DialogTitle>
                <Separator className="mb-6" />
                {active?.content}
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
