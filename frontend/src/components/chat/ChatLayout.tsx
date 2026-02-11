import { useEffect, useState } from "react"
import { useThreads } from "@/hooks/useThreads"
import { useChat } from "@/hooks/useChat"
import { ThreadSidebar } from "./ThreadSidebar"
import { MessageArea } from "./MessageArea"
import { MessageInput } from "./MessageInput"
import { WebResultsSidebar } from "./WebResultsSidebar"

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
    webResults,
  } = useChat(activeThreadId, updateThreadTitle)

  const [sidebarDismissed, setSidebarDismissed] = useState(false)

  // Reset dismissed state when new web results arrive
  useEffect(() => {
    if (webResults.length > 0) {
      setSidebarDismissed(false)
    }
  }, [webResults])

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
      const thread = await createThread()
      if (thread) {
        setTimeout(() => sendMessage(content), 50)
      }
      return
    }
    sendMessage(content)
  }

  const showSidebar = webResults.length > 0 && !sidebarDismissed

  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      <ThreadSidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelect={selectThread}
        onCreate={createThread}
        onDelete={deleteThread}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <MessageArea
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
        />
        <MessageInput onSend={handleSend} disabled={isStreaming} />
      </div>
      {showSidebar && (
        <WebResultsSidebar
          results={webResults}
          onClose={() => setSidebarDismissed(true)}
        />
      )}
    </div>
  )
}
