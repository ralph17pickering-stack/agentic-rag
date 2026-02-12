import { MessageSquarePlus } from "lucide-react"
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
              className={`flex items-center justify-between rounded-md px-4 py-3 text-sm cursor-pointer hover:bg-accent ${
                activeThreadId === thread.id ? "bg-accent" : ""
              }`}
              onClick={() => handleSelect(thread.id)}
            >
              <span className="truncate flex-1">{thread.title}</span>
              <button
                onClick={e => {
                  e.stopPropagation()
                  onDelete(thread.id)
                }}
                className="ml-3 text-muted-foreground hover:text-destructive"
              >
                &times;
              </button>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
