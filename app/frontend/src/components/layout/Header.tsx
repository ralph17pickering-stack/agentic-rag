import { useTheme } from "next-themes"
import { Sun, Moon, Monitor, Menu } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { Breakpoint } from "@/hooks/useBreakpoint"

type View = "chat" | "documents"

interface HeaderProps {
  email: string
  view: View
  onViewChange: (view: View) => void
  onSignOut: () => void
  breakpoint: Breakpoint
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  const cycle = () => {
    if (theme === "system") setTheme("light")
    else if (theme === "light") setTheme("dark")
    else setTheme("system")
  }

  const icon =
    theme === "light" ? <Sun className="h-4 w-4" /> :
    theme === "dark" ? <Moon className="h-4 w-4" /> :
    <Monitor className="h-4 w-4" />

  const label =
    theme === "light" ? "Light" :
    theme === "dark" ? "Dark" :
    "System"

  return (
    <Button variant="ghost" size="sm" onClick={cycle} className="gap-1.5" title={`Theme: ${label}`}>
      {icon}
      <span className="hidden sm:inline text-xs">{label}</span>
    </Button>
  )
}

export function Header({ email, view, onViewChange, onSignOut, breakpoint }: HeaderProps) {
  const isMobile = breakpoint === "mobile"

  return (
    <header className={`flex items-center justify-between border-b px-4 ${isMobile ? "h-12" : "h-14"}`}>
      <div className="flex items-center gap-3">
        <h1 className={`font-semibold ${isMobile ? "text-base" : "text-lg"}`}>Agentic RAG</h1>
        {!isMobile && (
          <nav className="flex gap-1">
            <Button
              variant={view === "chat" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => onViewChange("chat")}
            >
              Chat
            </Button>
            <Button
              variant={view === "documents" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => onViewChange("documents")}
            >
              Documents
            </Button>
          </nav>
        )}
      </div>
      <div className="flex items-center gap-1">
        <ThemeToggle />
        {isMobile ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <Menu className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onViewChange("documents")}>
                Documents
              </DropdownMenuItem>
              <DropdownMenuItem className="text-muted-foreground text-xs" disabled>
                {email}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onSignOut}>Sign Out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm">
                {email}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onSignOut}>Sign Out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </header>
  )
}
