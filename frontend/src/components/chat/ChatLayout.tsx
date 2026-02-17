import { useEffect, useState, useRef } from "react"
import { useThreads } from "@/hooks/useThreads"
import { useChat } from "@/hooks/useChat"
import { usePanelState } from "@/hooks/usePanelState"
import { LeftPanel } from "./LeftPanel"
import { RightPanel } from "./RightPanel"
import { Scrim } from "./Scrim"
import { MessageArea } from "./MessageArea"
import { MessageInput } from "./MessageInput"
import { BottomTabs, type MobileTab } from "./BottomTabs"
import { MobileHistoryView } from "./MobileHistoryView"
import { MobileResultsView } from "./MobileResultsView"
import type { Breakpoint } from "@/hooks/useBreakpoint"

interface ChatLayoutProps {
  breakpoint: Breakpoint
}

export function ChatLayout({ breakpoint }: ChatLayoutProps) {
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
    clearMessages,
    webResults,
    usedSources,
    currentStatus,
    usedDeepAnalysis,
  } = useChat(activeThreadId, updateThreadTitle)

  const {
    leftPanel,
    rightPanel,
    toggleLeftPanel,
    pinLeftPanel,
    unpinLeftPanel,
    openRightPanel,
    closeRightPanel,
    closeAllOverlays,
  } = usePanelState(breakpoint)

  const [mobileTab, setMobileTab] = useState<MobileTab>("chat")
  const [hasNewResults, setHasNewResults] = useState(false)
  const prevResultsLen = useRef(0)

  // Auto-open right panel on new web results (desktop/tablet)
  useEffect(() => {
    if (webResults.length > 0 && webResults.length !== prevResultsLen.current) {
      if (breakpoint !== "mobile") {
        openRightPanel()
      } else {
        setHasNewResults(true)
      }
    }
    prevResultsLen.current = webResults.length
  }, [webResults, breakpoint, openRightPanel])

  const prevSourcesLen = useRef(0)

  // Auto-open right panel on new citations (desktop/tablet)
  useEffect(() => {
    if (usedSources.length > 0 && usedSources.length !== prevSourcesLen.current) {
      if (breakpoint !== "mobile") {
        openRightPanel()
      }
    }
    prevSourcesLen.current = usedSources.length
  }, [usedSources, breakpoint, openRightPanel])

  // Clear badge when viewing results tab
  useEffect(() => {
    if (mobileTab === "results") {
      setHasNewResults(false)
    }
  }, [mobileTab])

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
        sendMessage(content, thread.id)
      }
      return
    }
    sendMessage(content)
  }

  const handleClearChat = async () => {
    if (!activeThreadId || messages.length === 0) return
    if (!window.confirm("Clear all messages in this chat? This cannot be undone.")) return
    await clearMessages(activeThreadId)
  }

  const isMobile = breakpoint === "mobile"
  const hasOverlay = leftPanel === "open-overlay" || rightPanel === "open-overlay"
  const leftPinned = leftPanel === "open-pinned"

  // Mobile layout
  if (isMobile) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        {mobileTab === "chat" && (
          <>
            <div className="flex min-w-0 flex-1 flex-col min-h-0">
              {activeThreadId && messages.length > 0 && (
                <div className="flex justify-end border-b px-3 py-1">
                  <button
                    onClick={handleClearChat}
                    className="text-xs text-muted-foreground hover:text-destructive transition-colors"
                    disabled={isStreaming}
                  >
                    Clear chat
                  </button>
                </div>
              )}
              <MessageArea
                messages={messages}
                streamingContent={streamingContent}
                isStreaming={isStreaming}
                currentStatus={currentStatus}
                usedDeepAnalysis={usedDeepAnalysis}
              />
              <MessageInput onSend={handleSend} disabled={isStreaming} />
            </div>
          </>
        )}
        {mobileTab === "history" && (
          <MobileHistoryView
            threads={threads}
            activeThreadId={activeThreadId}
            onSelect={selectThread}
            onCreate={createThread}
            onDelete={deleteThread}
            onNavigateToChat={() => setMobileTab("chat")}
          />
        )}
        {mobileTab === "results" && (
          <MobileResultsView results={webResults} />
        )}
        <BottomTabs
          active={mobileTab}
          onChange={setMobileTab}
          hasNewResults={hasNewResults}
        />
      </div>
    )
  }

  // Desktop / tablet layout
  const headerHeight = "3.5rem"

  return (
    <div className="relative flex overflow-hidden" style={{ height: `calc(100vh - ${headerHeight})` }}>
      {/* Left panel (pinned takes space, overlay is absolute) */}
      {leftPinned && (
        <div className="shrink-0 transition-[width] duration-250 ease-in-out" style={{ width: 280 }}>
          <LeftPanel
            threads={threads}
            activeThreadId={activeThreadId}
            state={leftPanel}
            onSelect={selectThread}
            onCreate={createThread}
            onDelete={deleteThread}
            onToggle={toggleLeftPanel}
            onPin={pinLeftPanel}
            onUnpin={unpinLeftPanel}
            canPin={breakpoint === "desktop"}
          />
        </div>
      )}

      {/* Rail (when not pinned) */}
      {!leftPinned && (
        <LeftPanel
          threads={threads}
          activeThreadId={activeThreadId}
          state={leftPanel}
          onSelect={(id) => {
            selectThread(id)
            if (leftPanel === "open-overlay") closeAllOverlays()
          }}
          onCreate={createThread}
          onDelete={deleteThread}
          onToggle={toggleLeftPanel}
          onPin={pinLeftPanel}
          onUnpin={unpinLeftPanel}
          canPin={breakpoint === "desktop"}
        />
      )}

      {/* Scrim for overlays */}
      <Scrim visible={hasOverlay} onClick={closeAllOverlays} />

      {/* Main chat area */}
      <div className="flex min-w-0 min-h-0 flex-1 flex-col">
        {activeThreadId && messages.length > 0 && (
          <div className="flex justify-end border-b px-3 py-1">
            <button
              onClick={handleClearChat}
              className="text-xs text-muted-foreground hover:text-destructive transition-colors"
              disabled={isStreaming}
            >
              Clear chat
            </button>
          </div>
        )}
        <MessageArea
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
          currentStatus={currentStatus}
          usedDeepAnalysis={usedDeepAnalysis}
        />
        <MessageInput onSend={handleSend} disabled={isStreaming} />
      </div>

      {/* Right panel */}
      <RightPanel
        results={webResults}
        usedSources={usedSources}
        state={rightPanel}
        onClose={closeRightPanel}
        onOpen={() => openRightPanel()}
      />
    </div>
  )
}
