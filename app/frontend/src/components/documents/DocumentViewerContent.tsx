import { useMemo } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { ExternalLink, FileText, Loader2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { Document } from "@/types"

const FILE_TYPE_LABELS: Record<string, string> = {
  pdf: "PDF", docx: "DOCX", txt: "TXT", md: "MD",
  csv: "CSV", html: "HTML", unknown: "DOC",
}

interface TocEntry {
  level: number
  text: string
  id: string
}

function buildToc(content: string): TocEntry[] {
  const lines = content.split("\n")
  const entries: TocEntry[] = []
  const seen: Record<string, number> = {}
  for (const line of lines) {
    const match = line.match(/^(#{1,3})\s+(.+)/)
    if (!match) continue
    const level = match[1].length
    const text = match[2].trim()
    const base = text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
    const id = seen[base] ? `${base}-${seen[base]++}` : base
    seen[base] = seen[base] ? seen[base] : 1
    entries.push({ level, text, id })
  }
  return entries
}

interface DocumentViewerContentProps {
  document: Document
  content: string
  loading: boolean
  error: string | null
  /** Show "Open full view ↗" button — true in the inline panel, false on the full-screen page */
  showOpenFullView?: boolean
  /** Render ToC in a separate aside column (for full-screen layout) vs sticky within scroll area */
  tocMode?: "inline" | "aside"
}

export function DocumentViewerContent({
  document,
  content,
  loading,
  error,
  showOpenFullView = true,
  tocMode = "inline",
}: DocumentViewerContentProps) {
  const toc = useMemo(() => (content ? buildToc(content) : []), [content])
  const displayTitle = document.title || document.filename

  return (
    <div className="flex flex-col h-full">
      {/* Metadata header */}
      <div className="shrink-0 border-b px-4 py-3 space-y-1.5">
        <div className="flex items-start gap-2">
          <Badge variant="secondary" className="shrink-0 mt-0.5 text-xs font-mono uppercase">
            {FILE_TYPE_LABELS[document.file_type] ?? document.file_type}
          </Badge>
          <h2 className="flex-1 text-sm font-semibold leading-tight line-clamp-2">{displayTitle}</h2>
          {showOpenFullView && (
            <a
              href={`/documents/${document.id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              title="Open full view"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Full view</span>
            </a>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {document.document_date && <span>{document.document_date}</span>}
          {document.source_url && (
            <a
              href={document.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 hover:text-foreground transition-colors truncate max-w-[200px]"
            >
              <ExternalLink className="h-3 w-3 shrink-0" />
              <span className="truncate">{new URL(document.source_url).hostname}</span>
            </a>
          )}
        </div>
        {document.topics && document.topics.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {document.topics.map((t) => (
              <Badge key={t} variant="outline" className="text-xs px-1.5 py-0">
                {t}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Body */}
      <div className={`flex flex-1 min-h-0 ${tocMode === "aside" ? "flex-row" : "flex-col"}`}>
        {/* ToC — aside mode (full-screen page) */}
        {tocMode === "aside" && toc.length > 0 && (
          <nav className="w-48 shrink-0 border-r p-4 overflow-y-auto text-xs space-y-1">
            <p className="font-semibold mb-2 text-foreground">Contents</p>
            {toc.map((entry) => (
              <a
                key={entry.id}
                href={`#${entry.id}`}
                className="block text-muted-foreground hover:text-foreground transition-colors truncate"
                style={{ paddingLeft: `${(entry.level - 1) * 12}px` }}
              >
                {entry.text}
              </a>
            ))}
          </nav>
        )}

        <ScrollArea className="flex-1">
          <div className="p-4">
            {/* ToC — inline mode (panel) */}
            {tocMode === "inline" && toc.length > 2 && (
              <nav className="mb-4 rounded-md border bg-muted/40 p-3 text-xs space-y-1">
                <p className="font-semibold mb-1.5 text-foreground">Contents</p>
                {toc.map((entry) => (
                  <a
                    key={entry.id}
                    href={`#${entry.id}`}
                    className="block text-muted-foreground hover:text-foreground transition-colors"
                    style={{ paddingLeft: `${(entry.level - 1) * 12}px` }}
                  >
                    {entry.text}
                  </a>
                ))}
              </nav>
            )}

            {/* Content states */}
            {loading && (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="size-5 animate-spin text-muted-foreground" />
              </div>
            )}
            {error && (
              <p className="text-sm text-destructive py-4">{error}</p>
            )}
            {!loading && !error && content && (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    // Add id anchors to headings for ToC navigation
                    h1: ({ children, ...props }) => {
                      const id = String(children).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
                      return <h1 id={id} {...props}>{children}</h1>
                    },
                    h2: ({ children, ...props }) => {
                      const id = String(children).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
                      return <h2 id={id} {...props}>{children}</h2>
                    },
                    h3: ({ children, ...props }) => {
                      const id = String(children).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
                      return <h3 id={id} {...props}>{children}</h3>
                    },
                  }}
                >
                  {content}
                </ReactMarkdown>
              </div>
            )}
            {!loading && !error && !content && (
              <div className="flex flex-col items-center justify-center py-16 gap-2 text-muted-foreground">
                <FileText className="size-8 opacity-40" />
                <p className="text-sm">No content available</p>
              </div>
            )}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}
