import { useEffect } from "react"
import { useThreads } from "@/hooks/useThreads"
import { useChat } from "@/hooks/useChat"
import { ThreadSidebar } from "./ThreadSidebar"
import { MessageArea } from "./MessageArea"
import { MessageInput } from "./MessageInput"

export function ChatLayout() {
  const {
    threads,
    activeThreadId,
    fetchThreads,
    createThread,
    deleteThread,
    updateThreadTitle,
    selectThread,
  } = useThreads()

  const {
    messages,
    isStreaming,
    streamingContent,
    fetchMessages,
    sendMessage,
    setMessages,
  } = useChat(activeThreadId, updateThreadTitle)

  useEffect(() => {
    fetchThreads()
  }, [fetchThreads])

  useEffect(() => {
    if (activeThreadId) {
      fetchMessages(activeThreadId)
    } else {
      setMessages([])
    }
  }, [activeThreadId, fetchMessages, setMessages])

  const handleSend = async (content: string) => {
    if (!activeThreadId) {
      // Auto-create thread if none selected
      const thread = await createThread()
      if (thread) {
        // Small delay to ensure state update, then send
        setTimeout(() => sendMessage(content), 50)
      }
      return
    }
    sendMessage(content)
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      <ThreadSidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelect={selectThread}
        onCreate={createThread}
        onDelete={deleteThread}
      />
      <div className="flex flex-1 flex-col">
        <MessageArea
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
        />
        <MessageInput onSend={handleSend} disabled={isStreaming} />
      </div>
    </div>
  )
}
