"use client"

import { cn } from "@app/core/lib/utils"
import { useServerStatus } from "@/hooks/use-server-status"
import {
  HoverCard,
  HoverCardTrigger,
  HoverCardContent,
} from "@app/ui/hover-card"
import { Badge } from "@app/ui/badge"
import { isDevelopment } from "@/lib/env-helpers"

export function ServerHealthIndicator() {
  const { status, isLoading, error } = useServerStatus()

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2">
        <div className="size-2 rounded-full bg-muted-foreground/20 animate-pulse" />
        <span className="text-xs text-muted-foreground font-mono">
          Loading...
        </span>
      </div>
    )
  }

  const statusColor =
    error || !status
      ? "bg-red-500"
      : status.status === "healthy"
        ? "bg-green-500"
        : status.status === "degraded"
          ? "bg-yellow-500"
          : "bg-red-500"

  const statusIndicator = (
    <div className="flex items-center gap-2 px-3 py-2 cursor-default">
      <div className="relative">
        <div
          className={cn("size-2 rounded-full transition-colors", statusColor)}
        />
        {status?.status === "healthy" && (
          <div
            className={cn(
              "absolute inset-0 size-2 rounded-full animate-ping",
              statusColor,
              "opacity-75",
            )}
          />
        )}
      </div>
      <span className="text-xs text-muted-foreground font-mono">
        v{status?.version || "0.0.0"}
      </span>
    </div>
  )

  if (!isDevelopment) {
    return statusIndicator
  }

  return (
    <HoverCard>
      <HoverCardTrigger>{statusIndicator}</HoverCardTrigger>
      <HoverCardContent side="top" align="start" className="w-64">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">Server Status</span>
            <Badge
              variant="secondary"
              className="text-[10px] px-1.5 py-0 h-4 font-mono"
            >
              {status?.environment || "unknown"}
            </Badge>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">API</span>
              <div className="flex items-center gap-1.5">
                <div
                  className={cn(
                    "size-1.5 rounded-full",
                    status?.components?.api === "healthy"
                      ? "bg-green-500"
                      : "bg-red-500",
                  )}
                />
                <span className="text-xs capitalize">
                  {status?.components?.api || "unknown"}
                </span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Database</span>
              <div className="flex items-center gap-1.5">
                <div
                  className={cn(
                    "size-1.5 rounded-full",
                    status?.components?.database?.status === "healthy"
                      ? "bg-green-500"
                      : "bg-red-500",
                  )}
                />
                <span className="text-xs capitalize">
                  {status?.components?.database?.status || "unknown"}
                </span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                Chatbot Agent
              </span>
              <div className="flex items-center gap-1.5">
                <div
                  className={cn(
                    "size-1.5 rounded-full",
                    status?.components?.agents?.chatbot?.ready
                      ? "bg-green-500"
                      : "bg-red-500",
                  )}
                />
                <span className="text-xs">
                  {status?.components?.agents?.chatbot?.ready
                    ? "Ready"
                    : "Not Ready"}
                </span>
              </div>
            </div>
          </div>
          {status?.timestamp && (
            <div className="pt-2 border-t">
              <span className="text-[10px] text-muted-foreground font-mono">
                Updated {new Date(status.timestamp).toLocaleTimeString()}
              </span>
            </div>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  )
}
