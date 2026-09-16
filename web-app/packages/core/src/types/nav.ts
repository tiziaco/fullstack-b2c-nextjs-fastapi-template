import type { ComponentType } from "react"

/**
 * Sidebar navigation entry.
 *
 * `icon` is typed structurally rather than as lucide-react's `LucideIcon` so
 * this package stays free of any one icon library: lucide's components remain
 * assignable, and a native app rendering lucide-react-native satisfies the
 * same contract. Renderers call it with no props today.
 */
export type NavItem = {
  title: string
  url: string
  icon?: ComponentType<{ className?: string }>
  items?: Array<{
    title: string
    url: string
  }>
}
