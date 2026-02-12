import { MessageSquare, Clock, Globe } from "lucide-react"

export type MobileTab = "chat" | "history" | "results"

interface BottomTabsProps {
  active: MobileTab
  onChange: (tab: MobileTab) => void
  hasNewResults: boolean
}

export function BottomTabs({ active, onChange, hasNewResults }: BottomTabsProps) {
  const tabs: { id: MobileTab; label: string; Icon: typeof MessageSquare }[] = [
    { id: "chat", label: "Chat", Icon: MessageSquare },
    { id: "history", label: "History", Icon: Clock },
    { id: "results", label: "Results", Icon: Globe },
  ]

  return (
    <nav className="flex h-14 shrink-0 items-stretch border-t bg-background pb-[env(safe-area-inset-bottom)]">
      {tabs.map(({ id, label, Icon }) => {
        const isActive = active === id
        return (
          <button
            key={id}
            onClick={() => onChange(id)}
            className={`flex flex-1 flex-col items-center justify-center gap-0.5 text-xs transition-colors ${
              isActive
                ? "text-foreground font-semibold"
                : "text-muted-foreground"
            }`}
          >
            <span className="relative">
              <Icon className={`h-5 w-5 ${isActive ? "fill-current" : ""}`} />
              {id === "results" && hasNewResults && !isActive && (
                <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-destructive" />
              )}
            </span>
            <span>{label}</span>
          </button>
        )
      })}
    </nav>
  )
}
