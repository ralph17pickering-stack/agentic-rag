import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { Thread } from "@/types"

interface ThreadSidebarProps {
  threads: Thread[]
  activeThreadId: string | null
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
}

export function ThreadSidebar({ threads, activeThreadId, onSelect, onCreate, onDelete }: ThreadSidebarProps) {
  return (
    <div className="flex h-full w-64 flex-col border-r">
      <div className="p-3">
        <Button onClick={onCreate} className="w-full" size="sm">
          New Chat
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="space-y-1 p-2">
          {threads.map(thread => (
            <div
              key={thread.id}
              className={`group flex items-center justify-between rounded-md px-3 py-2 text-sm cursor-pointer hover:bg-accent ${
                activeThreadId === thread.id ? "bg-accent" : ""
              }`}
              onClick={() => onSelect(thread.id)}
            >
              <span className="truncate flex-1">{thread.title}</span>
              <button
                onClick={e => {
                  e.stopPropagation()
                  onDelete(thread.id)
                }}
                className="ml-2 hidden text-muted-foreground hover:text-destructive group-hover:inline-block"
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
