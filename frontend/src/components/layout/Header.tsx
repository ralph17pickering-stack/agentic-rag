import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

type View = "chat" | "documents"

interface HeaderProps {
  email: string
  view: View
  onViewChange: (view: View) => void
  onSignOut: () => void
}

export function Header({ email, view, onViewChange, onSignOut }: HeaderProps) {
  return (
    <header className="flex h-14 items-center justify-between border-b px-4">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-semibold">Agentic RAG</h1>
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
      </div>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm">
            {email}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={onSignOut}>
            Sign Out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}
