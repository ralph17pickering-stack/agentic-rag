import { useCallback, useRef, useState } from "react"
import { Eye, ExternalLink, Pencil, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { DocumentViewer } from "@/components/documents/DocumentViewer"
import { EditMetadataModal } from "@/components/documents/EditMetadataModal"
import type { Document } from "@/types"

interface DocumentsPanelProps {
  documents: Document[]
  loading: boolean
  uploading: boolean
  onUpload: (file: File) => Promise<Document>
  onDelete: (id: string) => Promise<void>
  onUpdate: (id: string, updates: Partial<Pick<Document, "title" | "summary" | "topics" | "document_date">>) => Promise<Document>
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

function truncateUrl(url: string): string {
  try {
    const u = new URL(url)
    const path = u.pathname.length > 20 ? u.pathname.slice(0, 20) + "…" : u.pathname
    return u.hostname + path
  } catch {
    return url.length > 40 ? url.slice(0, 40) + "…" : url
  }
}

export function DocumentsPanel({
  documents,
  loading,
  uploading,
  onUpload,
  onDelete,
  onUpdate,
}: DocumentsPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [viewingDoc, setViewingDoc] = useState<Document | null>(null)
  const [editingDoc, setEditingDoc] = useState<Document | null>(null)
  const [activeTopics, setActiveTopics] = useState<Set<string>>(new Set())

  const toggleTopic = (topic: string) => {
    setActiveTopics(prev => {
      const next = new Set(prev)
      next.has(topic) ? next.delete(topic) : next.add(topic)
      return next
    })
  }

  const filteredDocs = activeTopics.size === 0
    ? documents
    : documents.filter(doc => doc.topics?.some(t => activeTopics.has(t)))

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

      {activeTopics.size > 0 && (
        <div className="flex flex-wrap items-center gap-1 mt-3">
          <span className="text-xs text-muted-foreground">Filtered by:</span>
          {[...activeTopics].map(topic => (
            <button
              key={topic}
              onClick={() => toggleTopic(topic)}
              className="inline-flex items-center gap-1 bg-primary text-primary-foreground text-xs rounded-full px-2 py-0.5 hover:bg-primary/80"
            >
              {topic} <X className="size-3" />
            </button>
          ))}
          <button
            onClick={() => setActiveTopics(new Set())}
            className="text-xs text-muted-foreground underline ml-1"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Document list */}
      <div className="mt-6 flex-1 overflow-y-auto">
        {loading ? (
          <p className="text-muted-foreground text-center">Loading...</p>
        ) : documents.length === 0 ? (
          <p className="text-muted-foreground text-center">
            No documents uploaded yet. Upload a file to get started.
          </p>
        ) : filteredDocs.length === 0 ? (
          <p className="text-muted-foreground text-center">
            No documents match the selected filter.
          </p>
        ) : (
          <div className="space-y-2">
            {filteredDocs.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between rounded-lg border p-3 group"
              >
                <div className="flex-1 min-w-0 mr-3">
                  <p
                    className={`font-medium truncate ${doc.status === "ready" ? "hover:underline cursor-pointer" : ""}`}
                    onClick={() => { if (doc.status === "ready") setViewingDoc(doc) }}
                  >
                    {doc.title || doc.filename}
                  </p>
                  {doc.title && (
                    <p className="text-xs text-muted-foreground truncate">{doc.filename}</p>
                  )}
                  {doc.source_url && (
                    <a
                      href={doc.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors mt-0.5 w-fit"
                      title={doc.source_url}
                    >
                      <ExternalLink className="h-3 w-3 shrink-0" />
                      <span className="truncate">{truncateUrl(doc.source_url)}</span>
                    </a>
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
                        <button
                          key={topic}
                          onClick={(e) => { e.stopPropagation(); toggleTopic(topic) }}
                          className={`text-xs rounded-full px-2 py-0.5 transition-colors ${
                            activeTopics.has(topic)
                              ? "bg-primary text-primary-foreground"
                              : "bg-primary/10 text-primary hover:bg-primary/20"
                          }`}
                        >
                          {topic}
                        </button>
                      ))}
                    </div>
                  )}
                  {doc.status === "error" && doc.error_message && (
                    <p className="text-xs text-red-600 mt-1 truncate">
                      {doc.error_message}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-8 text-muted-foreground hover:text-foreground"
                    onClick={(e) => { e.stopPropagation(); setEditingDoc(doc) }}
                    title="Edit metadata"
                  >
                    <Pencil className="size-4" />
                  </Button>
                  {doc.status === "ready" && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-foreground"
                      onClick={() => setViewingDoc(doc)}
                    >
                      <Eye className="size-4" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
                    onClick={() => onDelete(doc.id)}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <DocumentViewer
        document={viewingDoc}
        open={viewingDoc !== null}
        onClose={() => setViewingDoc(null)}
      />

      <EditMetadataModal
        document={editingDoc}
        open={editingDoc !== null}
        onClose={() => setEditingDoc(null)}
        onSave={onUpdate}
      />
    </div>
  )
}
