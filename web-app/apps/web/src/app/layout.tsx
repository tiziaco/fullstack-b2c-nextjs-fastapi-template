import { Inter } from "next/font/google"
import { ThemeProvider } from "@app/ui/theme-provider"
import { Toaster } from "@app/ui/sonner"
import { ClerkProvider } from "@clerk/nextjs"
import { AuthProvider } from "@app/auth"
import { QueryProvider } from "@/providers/query-provider"

import type { Metadata } from "next"
import "@/styles/globals.css"

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" })

export const metadata: Metadata = {
  title: "Template App",
  description:
    "Template App is a B2C application template — Clerk authentication, a role-gated FastAPI backend, and a generated API contract, ready to be built on.",
  icons: {
    icon: [
      { url: "/icons/favicon.ico", sizes: "any", type: "image/x-icon" },
      { url: "/icons/favicon-16x16.ico", sizes: "16x16", type: "image/x-icon" },
      { url: "/icons/favicon-32x32.ico", sizes: "32x32", type: "image/x-icon" },
    ],
    apple: [{ url: "/icons/favicon-ios-57x57.ico", sizes: "57x57" }],
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <ClerkProvider>
      <html lang="en" suppressHydrationWarning className={inter.variable}>
        <body className="antialiased min-h-screen bg-background">
          <AuthProvider>
            <QueryProvider>
              <ThemeProvider
                attribute="class"
                defaultTheme="system"
                enableSystem
                disableTransitionOnChange
              >
                {children}
                <Toaster position="bottom-right" />
              </ThemeProvider>
            </QueryProvider>
          </AuthProvider>
        </body>
      </html>
    </ClerkProvider>
  )
}
