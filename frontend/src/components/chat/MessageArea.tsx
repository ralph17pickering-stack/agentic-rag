import { useEffect, useRef } from "react"
import type { Message } from "@/types"

interface MessageAreaProps {
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
  currentStatus?: string | null
  usedDeepAnalysis?: boolean
}

export function MessageArea({ messages, streamingContent, isStreaming, currentStatus, usedDeepAnalysis }: MessageAreaProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  }, [messages, streamingContent])

  if (messages.length === 0 && !isStreaming) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground">
        Start a conversation
      </div>
    )
  }

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0">
      <div className="mx-auto max-w-3xl space-y-6 p-6">
        {messages.map(msg => (
          <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] rounded-lg px-4 py-2 ${
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted"
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
            </div>
          </div>
        ))}
        {isStreaming && streamingContent && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-lg bg-muted px-4 py-2">
              {usedDeepAnalysis && (
                <span className="mb-1 inline-block rounded bg-violet-600 px-1.5 py-0.5 text-xs font-medium text-white">
                  Deep Analysis
                </span>
              )}
              <p className="whitespace-pre-wrap">{streamingContent}</p>
            </div>
          </div>
        )}
        {isStreaming && !streamingContent && (
          <div className="flex justify-start">
            <div className="rounded-lg bg-muted px-4 py-2">
              <span className="animate-pulse whitespace-pre-line">{currentStatus || "Thinking..."}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
