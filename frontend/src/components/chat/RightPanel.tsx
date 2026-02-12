import { useState } from "react"
import { X, Globe } from "lucide-react"
import { Button } from "@/components/ui/button"
import { apiFetch } from "@/lib/api"
import type { WebResult } from "@/types"
import type { RightPanelState } from "@/hooks/usePanelState"

interface RightPanelProps {
  results: WebResult[]
  state: RightPanelState
  onClose: () => void
  onOpen: () => void
}

export function RightPanel({ results, state, onClose, onOpen }: RightPanelProps) {
  const [saving, setSaving] = useState<Record<string, "loading" | "saved" | "error">>({})

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
  const hasResults = results.length > 0

  return (
    <>
      {/* Edge tab handle — visible when closed with results */}
      {!isOpen && hasResults && (
        <button
          onClick={onOpen}
          className="fixed right-0 top-1/2 z-20 -translate-y-1/2 rounded-l-md border border-r-0 bg-background px-2 py-3 text-xs font-medium shadow-md hover:bg-accent transition-colors"
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
        <div className="flex items-center justify-between border-b px-3 py-2">
          <h3 className="text-sm font-medium">Web Results</h3>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto min-h-0">
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
        </div>
      </div>
    </>
  )
}
