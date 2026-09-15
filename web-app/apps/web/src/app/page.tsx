import { redirect } from "next/navigation"

export default function Page() {
  // Middleware handles unauthenticated users (redirects to /sign-in)
  // This page only runs for authenticated users
  redirect("/home")
}
