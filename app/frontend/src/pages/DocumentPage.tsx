import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { ArrowLeft, Pencil } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ThemeProvider } from "next-themes"
import { useAuth } from "@/hooks/useAuth"
import { LoginForm } from "@/components/auth/LoginForm"
import { SignUpForm } from "@/components/auth/SignUpForm"
import { EditMetadataModal } from "@/components/documents/EditMetadataModal"
import { DocumentViewerContent } from "@/components/documents/DocumentViewerContent"
import { apiFetch } from "@/lib/api"
import type { Document } from "@/types"

export function DocumentPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user, loading: authLoading, signIn, signUp } = useAuth()
  const [isSignUp, setIsSignUp] = useState(false)

  const [doc, setDoc] = useState<Document | null>(null)
  const [content, setContent] = useState("")
  const [contentLoading, setContentLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingDoc, setEditingDoc] = useState<Document | null>(null)

  useEffect(() => {
    if (!id || !user) return
    let cancelled = false

    // Fetch document metadata
    apiFetch(`/api/documents/${id}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Document not found (HTTP ${res.status})`)
        return res.json() as Promise<Document>
      })
      .then((d) => { if (!cancelled) setDoc(d) })
      .catch((err) => { if (!cancelled) setError(err.message) })

    // Fetch content
    apiFetch(`/api/documents/${id}/content`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.text()
      })
      .then((text) => { if (!cancelled) { setContent(text); setContentLoading(false) } })
      .catch(() => { if (!cancelled) setContentLoading(false) })

    return () => { cancelled = true }
  }, [id, user])

  const handleUpdate = async (docId: string, updates: Partial<Pick<Document, "title" | "summary" | "topics" | "document_date">>) => {
    const res = await apiFetch(`/api/documents/${docId}`, {
      method: "PATCH",
      body: JSON.stringify(updates),
    })
    if (!res.ok) throw new Error("Update failed")
    const updated: Document = await res.json()
    setDoc(updated)
    return updated
  }

  // Auth loading
  if (authLoading) {
    return (
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <div className="flex h-screen items-center justify-center">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </ThemeProvider>
    )
  }

  // Not authenticated — show login
  if (!user) {
    return (
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <div className="flex h-screen items-center justify-center">
          {isSignUp ? (
            <SignUpForm onSignUp={signUp} onToggle={() => setIsSignUp(false)} />
          ) : (
            <LoginForm onSignIn={signIn} onToggle={() => setIsSignUp(true)} />
          )}
        </div>
      </ThemeProvider>
    )
  }

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <div className="h-screen flex flex-col bg-background text-foreground">
        {/* Page header */}
        <header className="shrink-0 flex items-center gap-3 border-b px-4 py-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="gap-1">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <h1 className="flex-1 text-sm font-semibold truncate">
            {doc ? (doc.title || doc.filename) : "Loading…"}
          </h1>
          {doc && (
            <Button variant="ghost" size="sm" onClick={() => setEditingDoc(doc)} className="gap-1">
              <Pencil className="h-3.5 w-3.5" />
              Edit metadata
            </Button>
          )}
        </header>

        {/* Three-column body (desktop) / stacked (mobile) */}
        <div className="flex flex-1 min-h-0">
          {error ? (
            <div className="flex flex-1 items-center justify-center p-8">
              <p className="text-sm text-destructive">{error}</p>
            </div>
          ) : doc ? (
            <>
              {/* Metadata sidebar (desktop only) */}
              <aside className="hidden lg:flex w-56 shrink-0 border-r flex-col p-4 gap-3 text-xs text-muted-foreground overflow-y-auto">
                <div>
                  <p className="font-semibold text-foreground mb-1">File</p>
                  <p className="break-all">{doc.filename}</p>
                </div>
                {doc.document_date && (
                  <div>
                    <p className="font-semibold text-foreground mb-1">Date</p>
                    <p>{doc.document_date}</p>
                  </div>
                )}
                {doc.topics && doc.topics.length > 0 && (
                  <div>
                    <p className="font-semibold text-foreground mb-1">Topics</p>
                    <div className="flex flex-wrap gap-1">
                      {doc.topics.map((t) => (
                        <span key={t} className="rounded bg-muted px-1.5 py-0.5">{t}</span>
                      ))}
                    </div>
                  </div>
                )}
                {doc.chunk_count > 0 && (
                  <div>
                    <p className="font-semibold text-foreground mb-1">Chunks</p>
                    <p>{doc.chunk_count}</p>
                  </div>
                )}
                {doc.file_size > 0 && (
                  <div>
                    <p className="font-semibold text-foreground mb-1">Size</p>
                    <p>{doc.file_size < 1024 * 1024
                      ? `${(doc.file_size / 1024).toFixed(1)} KB`
                      : `${(doc.file_size / (1024 * 1024)).toFixed(1)} MB`}
                    </p>
                  </div>
                )}
                {doc.summary && (
                  <div>
                    <p className="font-semibold text-foreground mb-1">Summary</p>
                    <p className="leading-relaxed">{doc.summary}</p>
                  </div>
                )}
              </aside>

              {/* Main content — DocumentViewerContent with aside ToC */}
              <div className="flex-1 min-w-0 min-h-0 overflow-hidden">
                <DocumentViewerContent
                  document={doc}
                  content={content}
                  loading={contentLoading}
                  error={null}
                  showOpenFullView={false}
                  tocMode="aside"
                />
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center">
              <p className="text-muted-foreground text-sm">Loading document…</p>
            </div>
          )}
        </div>

        {/* Edit metadata modal */}
        {editingDoc && (
          <EditMetadataModal
            document={editingDoc}
            open
            onClose={() => setEditingDoc(null)}
            onSave={(updates) => handleUpdate(editingDoc.id, updates)}
          />
        )}
      </div>
    </ThemeProvider>
  )
}
