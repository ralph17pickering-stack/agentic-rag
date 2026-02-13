import { MessageSquarePlus, PanelLeftClose, Pin, PinOff, FileText, MessageSquare, Minus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { Thread } from "@/types"
import type { LeftPanelState } from "@/hooks/usePanelState"

interface LeftPanelProps {
  threads: Thread[]
  activeThreadId: string | null
  state: LeftPanelState
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
  onToggle: () => void
  onPin: () => void
  onUnpin: () => void
  canPin: boolean
}

function Rail({ onToggle, onCreate }: { onToggle: () => void; onCreate: () => void }) {
  return (
    <div className="flex h-full w-12 shrink-0 flex-col items-center border-r bg-muted/30 py-2 gap-1">
      <Button
        variant="ghost"
        size="icon"
        className="h-9 w-9"
        onClick={onToggle}
        title="History & tools (Ctrl+B)"
      >
        <MessageSquare className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-9 w-9"
        onClick={onCreate}
        title="New chat"
      >
        <MessageSquarePlus className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-9 w-9"
        onClick={() => {}}
        title="Documents"
        disabled
      >
        <FileText className="h-4 w-4" />
      </Button>
    </div>
  )
}

function ExpandedPanel({
  threads,
  activeThreadId,
  isPinned,
  isOpen,
  canPin,
  onSelect,
  onCreate,
  onDelete,
  onToggle,
  onPin,
  onUnpin,
}: {
  threads: Thread[]
  activeThreadId: string | null
  isPinned: boolean
  isOpen: boolean
  canPin: boolean
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
  onToggle: () => void
  onPin: () => void
  onUnpin: () => void
}) {
  return (
    <div
      className={`flex h-full w-[280px] shrink-0 flex-col border-r bg-background transition-transform duration-200 ${
        isPinned
          ? ""
          : `absolute left-12 top-0 z-30 shadow-lg ${isOpen ? "translate-x-0" : "-translate-x-[328px] pointer-events-none"}`
      }`}
      style={isPinned ? undefined : { transitionTimingFunction: isOpen ? "ease-out" : "ease-in" }}
    >
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-sm font-medium">History</span>
        <div className="flex items-center gap-0.5">
          {canPin && !isPinned && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onPin} title="Pin panel">
              <Pin className="h-3.5 w-3.5" />
            </Button>
          )}
          {isPinned && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onUnpin} title="Unpin panel">
              <PinOff className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onToggle} title="Close panel">
            <PanelLeftClose className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      <div className="p-2">
        <Button onClick={onCreate} className="w-full" size="sm">
          <MessageSquarePlus className="mr-2 h-4 w-4" />
          New Chat
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="space-y-0.5 p-2">
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
                className="ml-2 shrink-0 text-muted-foreground hover:text-destructive"
                title="Delete chat"
              >
                <Minus className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}

export function LeftPanel({
  threads,
  activeThreadId,
  state,
  onSelect,
  onCreate,
  onDelete,
  onToggle,
  onPin,
  onUnpin,
  canPin,
}: LeftPanelProps) {
  const isPinned = state === "open-pinned"
  const isOpen = state === "open-overlay"

  if (isPinned) {
    return (
      <ExpandedPanel
        threads={threads}
        activeThreadId={activeThreadId}
        isPinned
        isOpen
        canPin={canPin}
        onSelect={onSelect}
        onCreate={onCreate}
        onDelete={onDelete}
        onToggle={onToggle}
        onPin={onPin}
        onUnpin={onUnpin}
      />
    )
  }

  return (
    <>
      <Rail onToggle={onToggle} onCreate={onCreate} />
      <ExpandedPanel
        threads={threads}
        activeThreadId={activeThreadId}
        isPinned={false}
        isOpen={isOpen}
        canPin={canPin}
        onSelect={onSelect}
        onCreate={onCreate}
        onDelete={onDelete}
        onToggle={onToggle}
        onPin={onPin}
        onUnpin={onUnpin}
      />
    </>
  )
}
