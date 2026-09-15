import { Skeleton } from "@app/ui/skeleton"

export default function AppLoading() {
  return (
    <div className="space-y-4">
      {/* Page title skeleton */}
      <Skeleton className="h-8 w-48" />

      {/* Content skeleton */}
      <div className="grid gap-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    </div>
  )
}
