import { useState } from "react"
import { X, Globe, BookOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { apiFetch } from "@/lib/api"
import { useDocumentViewer } from "@/hooks/useDocumentViewer"
import type { WebResult, CitationSource } from "@/types"
import type { RightPanelState } from "@/hooks/usePanelState"

type PanelMode = "citations" | "web-results"

interface RightPanelProps {
  results: WebResult[]
  usedSources: CitationSource[]
  state: RightPanelState
  onClose: () => void
  onOpen: (mode: PanelMode) => void
}

export function RightPanel({ results, usedSources, state, onClose, onOpen }: RightPanelProps) {
  const { openDocumentById } = useDocumentViewer()
  const [saving, setSaving] = useState<Record<string, "loading" | "saved" | "error">>({})
  const [mode, setMode] = useState<PanelMode>("citations")

  const handleSave = async (result: WebResult) => {
    setSaving(prev => ({ ...prev, [result.url]: "loading" }))
    try {
      const res = await apiFetch("/api/documents/from-url", {
        method: "POST",
        body: JSON.stringify({ url: result.url, title: result.title }),
      })
      if (res.ok) {
        setSaving(prev => ({ ...prev, [result.url]: "saved" }))
      } else {
        setSaving(prev => ({ ...prev, [result.url]: "error" }))
      }
    } catch {
      setSaving(prev => ({ ...prev, [result.url]: "error" }))
    }
  }

  const isOpen = state === "open-overlay"
  const hasWebResults = results.length > 0
  const hasCitations = usedSources.length > 0

  return (
    <>
      {/* Citations edge handle — visible when closed with citations */}
      {!isOpen && hasCitations && (
        <button
          onClick={() => { setMode("citations"); onOpen("citations") }}
          className="fixed right-0 z-20 rounded-l-md border border-r-0 bg-background px-2 py-3 text-xs font-medium shadow-md hover:bg-accent transition-colors"
          style={{ top: "calc(50% - 3.5rem)" }}
          title="Show citations"
        >
          <BookOpen className="mx-auto mb-1 h-4 w-4" />
          <span className="[writing-mode:vertical-lr] text-[10px]">Sources ({usedSources.length})</span>
        </button>
      )}

      {/* Web results edge handle — visible when closed with results */}
      {!isOpen && hasWebResults && (
        <button
          onClick={() => { setMode("web-results"); onOpen("web-results") }}
          className="fixed right-0 z-20 rounded-l-md border border-r-0 bg-background px-2 py-3 text-xs font-medium shadow-md hover:bg-accent transition-colors"
          style={{ top: hasCitations ? "calc(50% + 1rem)" : "50%", transform: "translateY(-50%)" }}
          title="Show web results"
        >
          <Globe className="mx-auto mb-1 h-4 w-4" />
          <span className="[writing-mode:vertical-lr] text-[10px]">Results ({results.length})</span>
        </button>
      )}

      {/* Sliding panel */}
      <div
        className={`absolute right-0 top-0 z-30 flex h-full w-80 shrink-0 flex-col overflow-hidden border-l bg-background shadow-lg transition-transform duration-200 ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
        style={{ transitionTimingFunction: isOpen ? "ease-out" : "ease-in" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-3 py-2">
          <div className="flex items-center gap-2">
            {hasCitations && hasWebResults ? (
              <>
                <button
                  onClick={() => setMode("citations")}
                  className={`text-sm font-medium transition-colors ${mode === "citations" ? "text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                >
                  Sources
                </button>
                <span className="text-muted-foreground text-xs">/</span>
                <button
                  onClick={() => setMode("web-results")}
                  className={`text-sm font-medium transition-colors ${mode === "web-results" ? "text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                >
                  Web
                </button>
              </>
            ) : (
              <h3 className="text-sm font-medium">{mode === "citations" ? "Sources" : "Web Results"}</h3>
            )}
          </div>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {mode === "citations" && (
            <div className="p-3 space-y-3">
              {usedSources.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-4">No sources for this response</p>
              ) : (
                usedSources.map((source, i) => (
                  <button
                    key={source.chunk_id ?? i}
                    onClick={() => openDocumentById(source.document_id, source.doc_title)}
                    className="w-full text-left overflow-hidden rounded-md border bg-card p-3 space-y-1.5 hover:bg-accent transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-medium line-clamp-2 leading-snug">{source.doc_title}</p>
                      <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {Math.round(source.score * 100)}%
                      </span>
                    </div>
                    <p className="text-[10px] text-muted-foreground">Chunk {source.chunk_index + 1}</p>
                    <p className="text-xs text-muted-foreground line-clamp-4 break-words">{source.content_preview}</p>
                  </button>
                ))
              )}
            </div>
          )}

          {mode === "web-results" && (
            <div className="p-3 space-y-3">
              {results.map((r, i) => (
                <div key={i} className="overflow-hidden rounded-md border bg-card p-3 space-y-2">
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-sm font-medium text-primary hover:underline line-clamp-2 break-all"
                  >
                    {r.title || r.url}
                  </a>
                  {r.snippet && (
                    <p className="text-xs text-muted-foreground line-clamp-3 break-words">{r.snippet}</p>
                  )}
                  <p className="text-xs text-muted-foreground truncate">{r.url}</p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full h-7 text-xs"
                    disabled={saving[r.url] === "loading" || saving[r.url] === "saved"}
                    onClick={() => handleSave(r)}
                  >
                    {saving[r.url] === "loading"
                      ? "Saving..."
                      : saving[r.url] === "saved"
                        ? "Saved"
                        : saving[r.url] === "error"
                          ? "Retry Save"
                          : "Save to KB"}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
