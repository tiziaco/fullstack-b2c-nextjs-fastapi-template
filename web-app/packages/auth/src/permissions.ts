/**
 * Role definitions and utilities for RBAC.
 *
 * Portability seam: getUserRole() is the only function that knows how
 * the auth provider represents roles. When migrating providers, only
 * this function changes — all consumers remain unchanged.
 */

/**
 * Platform roles, sourced from Clerk publicMetadata.role.
 *
 * Platform roles only. A per-resource capability — group moderator, page
 * admin — is not a role: it is scoped, non-exclusive and revocable, and a
 * single-valued claim expresses none of the three. Model those as rows.
 */
export const Role = {
  USER: "user",
  ADMIN: "admin",
} as const

export type Role = (typeof Role)[keyof typeof Role]

/**
 * Convert a raw role claim to a Role value.
 *
 * Returns null when the claim is absent or unrecognised, so an unknown value
 * can never be treated as a valid role.
 *
 * @example
 * getUserRole("admin")   // → "admin"
 * getUserRole("hacker")  // → null
 * getUserRole(null)      // → null
 */
export function getUserRole(role: string | null | undefined): Role | null {
  if (!role) return null
  const values = Object.values(Role) as string[]
  if (!values.includes(role)) return null
  return role as Role
}

/** Returns true only for platform administrators. */
export function isAdmin(role: Role | null): boolean {
  return role === Role.ADMIN
}

/** Display labels — mapped in the frontend only. */
export const ROLE_LABELS: Record<Role, string> = {
  [Role.USER]: "User",
  [Role.ADMIN]: "Admin",
}
