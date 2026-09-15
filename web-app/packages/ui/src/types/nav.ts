import type { LucideIcon } from "lucide-react"

/**
 * Sidebar navigation entry.
 *
 * A UI contract, not an API contract: it is typed by LucideIcon and consumed
 * only by this package's sidebar components and each app's nav configuration.
 */
export type NavItem = {
  title: string
  url: string
  icon?: LucideIcon
  items?: Array<{
    title: string
    url: string
  }>
}
