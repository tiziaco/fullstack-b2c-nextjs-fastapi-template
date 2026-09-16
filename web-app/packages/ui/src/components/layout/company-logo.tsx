"use client"

import Image from "next/image"
import {
  SidebarMenu,
  SidebarMenuItem,
  useSidebar,
} from "../../primitives/sidebar"

interface CompanyLogoProps {
  src: string
  alt?: string
}

export function CompanyLogo({ src, alt = "Logo" }: CompanyLogoProps) {
  const { state } = useSidebar()

  return (
    <SidebarMenu className="mb-10">
      <SidebarMenuItem>
        <div className="flex items-center gap-2">
          {state === "collapsed" && (
            <Image
              src={src}
              alt={alt}
              width={40}
              height={40}
              className="h-10 w-10 object-contain"
            />
          )}
          {state !== "collapsed" && (
            <Image
              src={src}
              alt={alt}
              width={250}
              height={40}
              className="h-10 w-auto object-contain"
            />
          )}
        </div>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
