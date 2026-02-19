import { useEffect, useRef, useState } from "react"
import { X, Ban } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { Document } from "@/types"

interface EditMetadataModalProps {
  document: Document | null
  open: boolean
  onClose: () => void
  onSave: (
    id: string,
    updates: Partial<Pick<Document, "title" | "summary" | "topics" | "document_date">>
  ) => Promise<Document>
  onBlockTag?: (tag: string) => Promise<number>
}

export function EditMetadataModal({ document, open, onClose, onSave, onBlockTag }: EditMetadataModalProps) {
  const [localTitle, setLocalTitle] = useState("")
  const [localSummary, setLocalSummary] = useState("")
  const [localTopics, setLocalTopics] = useState<string[]>([])
  const [localDate, setLocalDate] = useState("")
  const [topicInput, setTopicInput] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const topicInputRef = useRef<HTMLInputElement>(null)

  // Reset fields whenever the modal opens with a document
  useEffect(() => {
    if (open && document) {
      setLocalTitle(document.title ?? "")
      setLocalSummary(document.summary ?? "")
      setLocalTopics(document.topics ?? [])
      setLocalDate(document.document_date ?? "")
      setTopicInput("")
      setError(null)
    }
  }, [open, document])

  const addTopic = (raw: string) => {
    const trimmed = raw.trim().replace(/,+$/, "")
    if (!trimmed) return
    if (!localTopics.includes(trimmed)) {
      setLocalTopics(prev => [...prev, trimmed])
    }
    setTopicInput("")
  }

  const handleTopicKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault()
      addTopic(topicInput)
    } else if (e.key === "Backspace" && topicInput === "" && localTopics.length > 0) {
      setLocalTopics(prev => prev.slice(0, -1))
    }
  }

  const removeTopic = (topic: string) => {
    setLocalTopics(prev => prev.filter(t => t !== topic))
  }

  const handleSave = async () => {
    if (!document) return
    // Flush any pending topic input
    if (topicInput.trim()) addTopic(topicInput)

    setSaving(true)
    setError(null)
    try {
      await onSave(document.id, {
        title: localTitle || null,
        summary: localSummary || null,
        topics: localTopics,
        document_date: localDate || null,
      })
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  if (!document) return null

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit Metadata</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          {/* Title */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium">Title</label>
            <Input
              value={localTitle}
              onChange={(e) => setLocalTitle(e.target.value)}
              placeholder="Document title"
            />
          </div>

          {/* Summary */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium">Summary</label>
            <textarea
              value={localSummary}
              onChange={(e) => setLocalSummary(e.target.value)}
              placeholder="Brief summary of the document"
              rows={3}
              className="border-input dark:bg-input/30 placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:ring-[3px] resize-none"
            />
          </div>

          {/* Topics */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium">Topics</label>
            <div
              className="border-input dark:bg-input/30 focus-within:border-ring focus-within:ring-ring/50 flex min-h-9 w-full flex-wrap items-center gap-1 rounded-md border bg-transparent px-3 py-1.5 shadow-xs transition-[color,box-shadow] focus-within:ring-[3px]"
              onClick={() => topicInputRef.current?.focus()}
            >
              {localTopics.map((topic) => (
                <span
                  key={topic}
                  className="inline-flex items-center gap-1 bg-primary/10 text-primary rounded-full px-2 py-0.5 text-xs"
                >
                  {topic}
                  {onBlockTag && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        onBlockTag(topic).then(() => removeTopic(topic))
                      }}
                      className="hover:text-destructive"
                      title="Block this tag from all documents"
                    >
                      <Ban className="size-3" />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); removeTopic(topic) }}
                    className="hover:text-destructive"
                  >
                    <X className="size-3" />
                  </button>
                </span>
              ))}
              <input
                ref={topicInputRef}
                value={topicInput}
                onChange={(e) => setTopicInput(e.target.value)}
                onKeyDown={handleTopicKeyDown}
                onBlur={() => addTopic(topicInput)}
                placeholder={localTopics.length === 0 ? "Add topics (Enter or comma to add)" : ""}
                className="min-w-24 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              />
            </div>
          </div>

          {/* Document date */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium">Document Date</label>
            <Input
              type="date"
              value={localDate}
              onChange={(e) => setLocalDate(e.target.value)}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
