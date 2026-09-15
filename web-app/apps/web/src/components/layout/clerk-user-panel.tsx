"use client"

import { useClerk } from "@clerk/nextjs"
import { useAppAuth } from "@app/auth"
import { UserDetailsPanel } from "@app/ui/layout/user-panel"

export function ClerkUserPanel() {
  const { isLoaded, user } = useAppAuth()
  const { signOut, openUserProfile } = useClerk()

  return (
    <UserDetailsPanel
      user={
        isLoaded && user
          ? {
              name:
                [user.firstName, user.lastName].filter(Boolean).join(" ") ||
                "User",
              email: user.primaryEmailAddress?.emailAddress ?? "No email",
              imageUrl: user.imageUrl,
            }
          : null
      }
      onSignOut={() => signOut()}
      onOpenProfile={() => openUserProfile()}
    />
  )
}
