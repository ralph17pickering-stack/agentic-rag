import { useState, useEffect, useCallback } from "react"
import { supabase } from "@/lib/supabase"
import { apiFetch } from "@/lib/api"
import type { Document } from "@/types"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8001"

export function useDocuments() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)

  const fetchDocuments = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiFetch("/api/documents")
      if (res.ok) {
        setDocuments(await res.json())
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const uploadDocument = useCallback(async (file: File) => {
    setUploading(true)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      const formData = new FormData()
      formData.append("file", file)

      const res = await fetch(`${API_URL}/api/documents`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: formData,
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Upload failed" }))
        throw new Error(err.detail || "Upload failed")
      }

      const doc = await res.json()
      setDocuments(prev => [doc, ...prev])
      return doc
    } finally {
      setUploading(false)
    }
  }, [])

  const deleteDocument = useCallback(async (id: string) => {
    const res = await apiFetch(`/api/documents/${id}`, { method: "DELETE" })
    if (res.ok) {
      setDocuments(prev => prev.filter(d => d.id !== id))
    }
  }, [])

  // Supabase Realtime subscription for document status updates
  useEffect(() => {
    const channel = supabase
      .channel("documents-status")
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "documents" },
        (payload) => {
          const updated = payload.new as Document
          setDocuments(prev =>
            prev.map(d => (d.id === updated.id ? updated : d))
          )
        }
      )
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [])

  return { documents, loading, uploading, fetchDocuments, uploadDocument, deleteDocument }
}
