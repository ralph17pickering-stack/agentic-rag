import { MessageSquarePlus, Minus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { Thread } from "@/types"

interface MobileHistoryViewProps {
  threads: Thread[]
  activeThreadId: string | null
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
  onNavigateToChat: () => void
}

export function MobileHistoryView({
  threads,
  activeThreadId,
  onSelect,
  onCreate,
  onDelete,
  onNavigateToChat,
}: MobileHistoryViewProps) {
  const handleSelect = (id: string) => {
    onSelect(id)
    onNavigateToChat()
  }

  return (
    <div className="flex flex-1 flex-col min-h-0">
      <div className="p-3 border-b">
        <Button onClick={onCreate} className="w-full" size="sm">
          <MessageSquarePlus className="mr-2 h-4 w-4" />
          New Chat
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="space-y-0.5 p-2">
          {threads.length === 0 && (
            <p className="p-4 text-center text-sm text-muted-foreground">No conversations yet</p>
          )}
          {threads.map(thread => (
            <div
              key={thread.id}
              className={`grid grid-cols-[1fr_auto] items-center gap-1 rounded-md px-4 py-3 text-sm cursor-pointer hover:bg-accent ${
                activeThreadId === thread.id ? "bg-accent" : ""
              }`}
              onClick={() => handleSelect(thread.id)}
            >
              <span className="truncate">{thread.title}</span>
              <button
                onClick={e => {
                  e.stopPropagation()
                  onDelete(thread.id)
                }}
                className="rounded p-0.5 hover:text-red-500"
                style={{ color: '#94a3b8' }}
                title="Delete chat"
              >
                <Minus className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
