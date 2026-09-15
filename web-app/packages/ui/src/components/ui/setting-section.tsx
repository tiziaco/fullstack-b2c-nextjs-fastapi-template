import { ReactNode } from "react"

interface SettingSectionProps {
  title: string
  children: ReactNode
}

export function SettingSection({ title, children }: SettingSectionProps) {
  return (
    <div className="mb-4">
      <h3 className="text-sm font-semibold mb-2">{title}</h3>
      <div className="space-y-2">{children}</div>
    </div>
  )
}
