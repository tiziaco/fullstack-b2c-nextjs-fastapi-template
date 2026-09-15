/**
 * AuthProvider and useAppAuth hook.
 *
 * Portability seam: AuthProvider wraps Clerk's hooks to derive identity and role.
 * When migrating to WorkOS, only AuthProvider's internals change.
 * All components call useAppAuth() — they never call useAuth() or useUser() directly.
 */
"use client"

import { createContext, useContext } from "react"
import { useAuth, useUser } from "@clerk/nextjs"
import type { UserResource } from "@clerk/types"
import { getUserRole, Role } from "./permissions"

interface AuthContextValue {
  /** The Clerk user object, or null/undefined while loading. */
  user: UserResource | null | undefined
  /** The current user's platform role, or null if absent or unrecognised. */
  role: Role | null
  /** True once Clerk has finished initialising the session. */
  isLoaded: boolean
  /**
   * A fresh JWT for the current session, or null when signed out. The only
   * sanctioned way to reach a bearer token: @app/api-client's mutator consumes
   * it, which is what keeps that package off Clerk and on this seam.
   */
  getToken: () => Promise<string | null>
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  role: null,
  isLoaded: false,
  getToken: async () => null,
})

/** Wrap inside ClerkProvider in each app's root layout. */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { isLoaded, sessionClaims, getToken } = useAuth()
  const { user } = useUser()
  const role = getUserRole(sessionClaims?.role as string | undefined)

  return (
    <AuthContext.Provider value={{ user, role, isLoaded, getToken }}>
      {children}
    </AuthContext.Provider>
  )
}

/**
 * Hook for the current user's identity and role.
 *
 * Never call useAuth() or useUser() directly in a component, and always check
 * isLoaded before rendering role-dependent UI.
 */
export function useAppAuth(): AuthContextValue {
  return useContext(AuthContext)
}
