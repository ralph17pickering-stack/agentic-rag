import { describe, it, expect } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { DocumentViewerProvider, useDocumentViewer } from "../useDocumentViewer"
import type { Document } from "@/types"

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <DocumentViewerProvider>{children}</DocumentViewerProvider>
)

const mockDoc: Document = {
  id: "doc-1",
  user_id: "user-1",
  filename: "test.md",
  storage_path: "path/test.md",
  file_type: "md",
  file_size: 1024,
  status: "ready",
  error_message: null,
  chunk_count: 5,
  content_hash: null,
  title: "Test Document",
  summary: null,
  topics: ["testing"],
  document_date: "2024-01-01",
  source_url: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
}

describe("useDocumentViewer", () => {
  it("starts closed with no document", () => {
    const { result } = renderHook(() => useDocumentViewer(), { wrapper })
    expect(result.current.isOpen).toBe(false)
    expect(result.current.viewingDoc).toBeNull()
  })

  it("openDocument sets doc and opens panel", () => {
    const { result } = renderHook(() => useDocumentViewer(), { wrapper })
    act(() => { result.current.openDocument(mockDoc) })
    expect(result.current.isOpen).toBe(true)
    expect(result.current.viewingDoc).toEqual(mockDoc)
  })

  it("closeDocument closes panel", () => {
    const { result } = renderHook(() => useDocumentViewer(), { wrapper })
    act(() => { result.current.openDocument(mockDoc) })
    act(() => { result.current.closeDocument() })
    expect(result.current.isOpen).toBe(false)
  })

  it("throws when used outside provider", () => {
    expect(() => renderHook(() => useDocumentViewer())).toThrow()
  })
})
