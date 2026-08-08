"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useTheme } from "next-themes"
import { HomeIcon, TrendingUpIcon, FileTextIcon, MessageSquareIcon, CommandIcon, SearchIcon, SunIcon, MoonIcon } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

const navItems = [
  { title: "Home", url: "/", icon: HomeIcon },
  { title: "Dashboard", url: "/dashboard", icon: FileTextIcon },
  { title: "Trend", url: "/trends", icon: TrendingUpIcon },
  { title: "Feedback", url: "/feedback", icon: MessageSquareIcon },
]

interface AppNavbarProps {
  /** Override the active item. If omitted, determined from pathname. */
  activePage?: string
}

export function AppNavbar({ activePage }: AppNavbarProps) {
  const pathname = usePathname()
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  function isActive(item: (typeof navItems)[number]) {
    if (activePage) return activePage === item.title
    return pathname === item.url || (item.url !== "/" && pathname.startsWith(item.url))
  }

  return (
    <header className="flex w-full py-2 shrink-0 items-center justify-center bg-sidebar px-4">
      <div className="flex items-center gap-4">
        {/* Logo */}
        <Link
          href="/"
          className="flex items-center gap-2 rounded-md px-2 py-1 hover:bg-accent transition-colors"
        >
          <div className="flex size-7 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <CommandIcon className="size-4" />
          </div>
          <span className="text-base font-semibold">Aware</span>
        </Link>

        {/* Search */}
        <div className="relative w-48">
          <SearchIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
          <Input
            type="search"
            placeholder="Search..."
            className="pl-8 h-8 w-full text-sm"
          />
        </div>

        {/* Nav items */}
        <nav className="flex items-center gap-1">
          {navItems.map(({ title, url, icon: Icon }) => (
            <Link
              key={title}
              href={url}
              className={[
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                isActive({ title, url, icon: Icon })
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              ].join(" ")}
            >
              <Icon className="size-4" />
              <span>{title}</span>
            </Link>
          ))}
        </nav>

        {/* Theme Toggle */}
        <button
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors ml-2"
          aria-label="Toggle theme"
        >
          {mounted ? (
            resolvedTheme === "dark" ? (
              <MoonIcon className="size-4" />
            ) : (
              <SunIcon className="size-4" />
            )
          ) : (
            <div className="size-4" />
          )}
        </button>
      </div>
    </header>
  )
}
