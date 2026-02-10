import { useState, useCallback } from "react"
import { apiFetch } from "@/lib/api"
import type { Thread } from "@/types"

export function useThreads() {
  const [threads, setThreads] = useState<Thread[]>([])
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const fetchThreads = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiFetch("/api/threads")
      if (res.ok) {
        const data = await res.json()
        setThreads(data)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const createThread = useCallback(async () => {
    const res = await apiFetch("/api/threads", {
      method: "POST",
      body: JSON.stringify({ title: "New Chat" }),
    })
    if (res.ok) {
      const thread = await res.json()
      setThreads(prev => [thread, ...prev])
      setActiveThreadId(thread.id)
      return thread
    }
  }, [])

  const deleteThread = useCallback(async (id: string) => {
    const res = await apiFetch(`/api/threads/${id}`, { method: "DELETE" })
    if (res.ok) {
      setThreads(prev => prev.filter(t => t.id !== id))
      setActiveThreadId(prev => prev === id ? null : prev)
    }
  }, [])

  const updateThreadTitle = useCallback((id: string, title: string) => {
    setThreads(prev => prev.map(t => t.id === id ? { ...t, title } : t))
  }, [])

  const selectThread = useCallback((id: string) => {
    setActiveThreadId(id)
  }, [])

  return {
    threads,
    activeThreadId,
    loading,
    fetchThreads,
    createThread,
    deleteThread,
    updateThreadTitle,
    selectThread,
  }
}
