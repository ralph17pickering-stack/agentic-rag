import { useEffect, useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { apiFetch } from "@/lib/api"
import type { Document } from "@/types"
import { ExternalLink, Loader2 } from "lucide-react"

interface DocumentViewerProps {
  document: Document | null
  open: boolean
  onClose: () => void
}

export function DocumentViewer({ document, open, onClose }: DocumentViewerProps) {
  const [content, setContent] = useState<string>("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !document) return

    let cancelled = false
    setLoading(true)
    setError(null)
    setContent("")

    apiFetch(`/api/documents/${document.id}/content`)
      .then(async (res) => {
        if (!res.ok) {
          const msg = await res.text()
          throw new Error(msg || `HTTP ${res.status}`)
        }
        return res.text()
      })
      .then((text) => {
        if (!cancelled) setContent(text)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [open, document])

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="sm:max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-start justify-between gap-3 pr-8">
            <DialogTitle className="truncate">
              {document?.title || document?.filename}
            </DialogTitle>
            {document?.source_url && (
              <a
                href={document.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors mt-0.5"
                title={document.source_url}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                View original
              </a>
            )}
          </div>
          {document?.title && (
            <DialogDescription className="truncate">
              {document.filename}
            </DialogDescription>
          )}
        </DialogHeader>

        <ScrollArea className="h-[65vh]">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          )}
          {error && (
            <p className="text-sm text-red-600 py-4">{error}</p>
          )}
          {!loading && !error && (
            <div className="whitespace-pre-wrap font-sans text-sm leading-relaxed pr-4">
              {content}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}
