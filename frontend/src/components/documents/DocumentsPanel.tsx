import { useCallback, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import type { Document } from "@/types"

interface DocumentsPanelProps {
  documents: Document[]
  loading: boolean
  uploading: boolean
  onUpload: (file: File) => Promise<Document>
  onDelete: (id: string) => Promise<void>
}

const STATUS_COLORS: Record<Document["status"], string> = {
  pending: "bg-yellow-100 text-yellow-800",
  processing: "bg-blue-100 text-blue-800",
  ready: "bg-green-100 text-green-800",
  error: "bg-red-100 text-red-800",
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00")
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

export function DocumentsPanel({
  documents,
  loading,
  uploading,
  onUpload,
  onDelete,
}: DocumentsPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  const handleFile = useCallback(
    async (file: File) => {
      setError(null)
      setInfo(null)
      const ext = file.name.split(".").pop()?.toLowerCase()
      if (!ext || !["txt", "md", "pdf", "docx", "csv", "html"].includes(ext)) {
        setError("Only .txt, .md, .pdf, .docx, .csv, and .html files are supported")
        return
      }
      try {
        const doc = await onUpload(file)
        if (doc.is_duplicate) {
          setInfo(`${file.name} is already uploaded with identical content. Skipped.`)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Upload failed")
      }
    },
    [onUpload]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile]
  )

  return (
    <div className="flex flex-col h-full p-6 max-w-3xl mx-auto w-full">
      {/* Upload area */}
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          dragOver
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-muted-foreground/50"
        }`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.pdf,.docx,.csv,.html"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleFile(file)
            e.target.value = ""
          }}
        />
        <p className="text-muted-foreground">
          {uploading
            ? "Uploading..."
            : "Drop a file here, or click to browse"}
        </p>
      </div>

      {error && (
        <p className="text-sm text-red-600 mt-2">{error}</p>
      )}

      {info && (
        <p className="text-sm text-blue-600 mt-2">{info}</p>
      )}

      {/* Document list */}
      <div className="mt-6 flex-1 overflow-y-auto">
        {loading ? (
          <p className="text-muted-foreground text-center">Loading...</p>
        ) : documents.length === 0 ? (
          <p className="text-muted-foreground text-center">
            No documents uploaded yet. Upload a file to get started.
          </p>
        ) : (
          <div className="space-y-2">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between rounded-lg border p-3 group"
              >
                <div className="flex-1 min-w-0 mr-3">
                  <p className="font-medium truncate">{doc.title || doc.filename}</p>
                  {doc.title && (
                    <p className="text-xs text-muted-foreground truncate">{doc.filename}</p>
                  )}
                  <div className="flex items-center gap-3 text-sm text-muted-foreground mt-1">
                    <span>{formatSize(doc.file_size)}</span>
                    {doc.document_date && (
                      <span>{formatDate(doc.document_date)}</span>
                    )}
                    {doc.status === "ready" && (
                      <span>{doc.chunk_count} chunks</span>
                    )}
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[doc.status]}`}
                    >
                      {doc.status}
                    </span>
                  </div>
                  {doc.status === "ready" && doc.summary && (
                    <p className="text-xs text-muted-foreground mt-1 truncate">{doc.summary}</p>
                  )}
                  {doc.topics && doc.topics.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {doc.topics.map((topic) => (
                        <span
                          key={topic}
                          className="bg-primary/10 text-primary text-xs rounded-full px-2 py-0.5"
                        >
                          {topic}
                        </span>
                      ))}
                    </div>
                  )}
                  {doc.status === "error" && doc.error_message && (
                    <p className="text-xs text-red-600 mt-1 truncate">
                      {doc.error_message}
                    </p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
                  onClick={() => onDelete(doc.id)}
                >
                  Delete
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
