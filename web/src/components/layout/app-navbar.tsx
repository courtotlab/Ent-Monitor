"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useTheme } from "next-themes"
import { HomeIcon, TrendingUpIcon, FileTextIcon, MessageSquareIcon, CommandIcon, SearchIcon, SunIcon, MoonIcon, MenuIcon, XIcon } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

const navItems = [
  { title: "Home", url: "/", icon: HomeIcon },
  { title: "Dashboard", url: "/dashboard", icon: FileTextIcon },
  { title: "Trend", url: "/trends", icon: TrendingUpIcon },
  // { title: "Feedback", url: "/feedback", icon: MessageSquareIcon },
]

interface AppNavbarProps {
  activePage?: string
}

export function AppNavbar({ activePage }: AppNavbarProps) {
  const pathname = usePathname()
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)
  const [isMenuOpen, setIsMenuOpen] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  function isActive(item: (typeof navItems)[number]) {
    if (activePage) return activePage === item.title
    return pathname === item.url || (item.url !== "/" && pathname.startsWith(item.url))
  }

  return (
    <header className="flex w-full flex-col shrink-0 bg-sidebar border-b border-transparent">
      <div className="flex w-full py-2 px-4 items-center justify-between min-[500px]:justify-center min-[500px]:gap-4">
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

        {/* Desktop Nav items */}
        <nav className="hidden min-[500px]:flex items-center gap-1">
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

        <div className="flex items-center gap-2">
          {/* Theme Toggle */}
          <button
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors min-[500px]:ml-2"
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

          {/* Mobile Menu Toggle */}
          <button
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            className="flex min-[500px]:hidden h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            aria-label="Toggle menu"
          >
            {isMenuOpen ? <XIcon className="size-4" /> : <MenuIcon className="size-4" />}
          </button>
        </div>
      </div>

      {/* Mobile Nav Menu */}
      <div
        className={`grid transition-all duration-300 ease-in-out min-[500px]:hidden ${
          isMenuOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
        }`}
      >
        <div className="overflow-hidden">
          <nav className="flex flex-col gap-1 px-4 pb-4">
            {navItems.map(({ title, url, icon: Icon }) => (
              <Link
                key={title}
                href={url}
                onClick={() => setIsMenuOpen(false)}
                className={[
                  "flex items-center gap-3 rounded-md px-4 py-2 text-sm font-medium transition-colors w-full",
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
        </div>
      </div>
    </header>
  )
}
