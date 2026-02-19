import { createContext, useContext, useState, useCallback, type ReactNode } from "react"
import type { Document } from "@/types"
import { apiFetch } from "@/lib/api"

interface DocumentViewerContextValue {
  viewingDoc: Document | null
  isOpen: boolean
  openDocument: (doc: Document) => void
  openDocumentById: (id: string, fallbackTitle?: string) => Promise<void>
  closeDocument: () => void
}

const DocumentViewerContext = createContext<DocumentViewerContextValue | null>(null)

export function DocumentViewerProvider({ children }: { children: ReactNode }) {
  const [viewingDoc, setViewingDoc] = useState<Document | null>(null)
  const [isOpen, setIsOpen] = useState(false)

  const openDocument = useCallback((doc: Document) => {
    setViewingDoc(doc)
    setIsOpen(true)
  }, [])

  const openDocumentById = useCallback(async (id: string, fallbackTitle?: string) => {
    // Try to fetch full document metadata; fall back to a minimal object
    try {
      const res = await apiFetch(`/api/documents/${id}`)
      if (res.ok) {
        const doc: Document = await res.json()
        setViewingDoc(doc)
        setIsOpen(true)
        return
      }
    } catch {
      // ignore, use fallback
    }
    // Fallback: open with minimal info so content can still be fetched
    setViewingDoc({
      id,
      user_id: "",
      filename: fallbackTitle || "Document",
      storage_path: "",
      file_type: "unknown",
      file_size: 0,
      status: "ready",
      error_message: null,
      chunk_count: 0,
      content_hash: null,
      title: fallbackTitle || null,
      summary: null,
      topics: [],
      document_date: null,
      source_url: null,
      created_at: "",
      updated_at: "",
    } satisfies Document)
    setIsOpen(true)
  }, [])

  const closeDocument = useCallback(() => {
    setIsOpen(false)
    // Delay clearing doc so the close animation can finish
    setTimeout(() => setViewingDoc(null), 250)
  }, [])

  return (
    <DocumentViewerContext.Provider
      value={{ viewingDoc, isOpen, openDocument, openDocumentById, closeDocument }}
    >
      {children}
    </DocumentViewerContext.Provider>
  )
}

export function useDocumentViewer() {
  const ctx = useContext(DocumentViewerContext)
  if (!ctx) throw new Error("useDocumentViewer must be used within DocumentViewerProvider")
  return ctx
}
