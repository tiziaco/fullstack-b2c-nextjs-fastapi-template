"use client"

import { HomeIcon } from "lucide-react"
import type { NavItem } from "@app/core/types/nav"

/**
 * Default hub navigation (used by HubSidebar when no items prop is provided)
 */
export const HUB_NAV: NavItem[] = [
  { title: "Home", url: "/home", icon: HomeIcon },
  // { title: "Your Section", url: "/your-section", icon: SomeIcon },
]
