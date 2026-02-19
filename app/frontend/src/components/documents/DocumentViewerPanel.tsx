import { useEffect, useState } from "react"
import { X } from "lucide-react"
import { apiFetch } from "@/lib/api"
import { useDocumentViewer } from "@/hooks/useDocumentViewer"
import { useBreakpoint } from "@/hooks/useBreakpoint"
import { DocumentViewerContent } from "./DocumentViewerContent"
import { Scrim } from "@/components/chat/Scrim"

export function DocumentViewerPanel() {
  const { viewingDoc, isOpen, closeDocument } = useDocumentViewer()
  const breakpoint = useBreakpoint()
  const isMobile = breakpoint === "mobile"

  const [content, setContent] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch content when document changes
  useEffect(() => {
    if (!viewingDoc) {
      setContent("")
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    setContent("")

    apiFetch(`/api/documents/${viewingDoc.id}/content`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.text()
      })
      .then((text) => { if (!cancelled) setContent(text) })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [viewingDoc?.id])

  if (isMobile) {
    // Bottom drawer — always in DOM for smooth animation
    return (
      <>
        <Scrim visible={isOpen} onClick={closeDocument} />
        <div
          className="fixed bottom-0 inset-x-0 z-40 flex flex-col bg-background border-t shadow-2xl rounded-t-xl"
          style={{
            height: "78vh",
            transform: isOpen ? "translateY(0)" : "translateY(100%)",
            transition: "transform 200ms ease-in-out",
          }}
        >
          <div className="flex items-center justify-between px-4 py-2 border-b shrink-0">
            <div className="mx-auto w-10 h-1 rounded-full bg-muted-foreground/30" />
            <button
              onClick={closeDocument}
              className="ml-auto p-1 rounded hover:bg-accent transition-colors"
              aria-label="Close document viewer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          {viewingDoc && (
            <div className="flex-1 min-h-0 overflow-hidden">
              <DocumentViewerContent
                document={viewingDoc}
                content={content}
                loading={loading}
                error={error}
                showOpenFullView
                tocMode="inline"
              />
            </div>
          )}
        </div>
      </>
    )
  }

  // Desktop / tablet — flex column in the app layout row
  return (
    <div
      className="shrink-0 border-l bg-background flex flex-col overflow-hidden"
      style={{
        width: isOpen ? "40%" : "0",
        transition: "width 200ms ease-in-out",
      }}
    >
      {/* Close button */}
      <div className="flex items-center justify-between px-3 py-2 border-b shrink-0">
        <span className="text-xs text-muted-foreground font-medium uppercase tracking-wide">Document</span>
        <button
          onClick={closeDocument}
          className="p-1 rounded hover:bg-accent transition-colors"
          aria-label="Close document viewer"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      {viewingDoc && (
        <div className="flex-1 min-h-0 overflow-hidden">
          <DocumentViewerContent
            document={viewingDoc}
            content={content}
            loading={loading}
            error={error}
            showOpenFullView
            tocMode="inline"
          />
        </div>
      )}
    </div>
  )
}
