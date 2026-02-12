import { useState } from "react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { apiFetch } from "@/lib/api"
import type { WebResult } from "@/types"

interface MobileResultsViewProps {
  results: WebResult[]
}

export function MobileResultsView({ results }: MobileResultsViewProps) {
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

  if (results.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground text-sm">
        No web results yet
      </div>
    )
  }

  return (
    <ScrollArea className="flex-1">
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
            <p className="text-xs text-muted-foreground truncate break-all">{r.url}</p>
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
    </ScrollArea>
  )
}
