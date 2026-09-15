import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server"
import { NextResponse } from "next/server"

const isPublicRoute = createRouteMatcher(["/sign-in(.*)", "/sign-up(.*)"])

export default clerkMiddleware(async (auth, req) => {
  // `/` is an alias for `/home`, and the redirect has to happen here rather
  // than in an `app/page.tsx` calling redirect(). A page-level redirect reaches
  // a client-side navigation as a flight-stream error, not an HTTP redirect,
  // and the App Router deadlocks on one during the transition that follows
  // Clerk's setActive() — blank page, URL stuck on `/`, recoverable only by a
  // manual reload. Redirecting before auth.protect() also keeps `/` out of the
  // ?redirect_url= that a bounced visitor carries into sign-in, so they come
  // back to `/home` directly instead of through `/`.
  if (req.nextUrl.pathname === "/") {
    return NextResponse.redirect(new URL("/home", req.url))
  }

  // Allow public routes (sign-in, sign-up) without auth
  if (isPublicRoute(req)) return

  // Every signed-in user may use the app. Role gating belongs on the routes
  // that need it: add a matcher here (e.g. /admin(.*)) reading
  // sessionClaims.role through getUserRole() when such routes exist.
  await auth.protect()
})

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes
    "/(api|trpc)(.*)",
  ],
}
