import { useState, useEffect, useCallback } from "react"
import { apiFetch } from "@/lib/api"

export interface BlockedTag {
  id: string
  tag: string
  created_at: string
}

export function useBlockedTags() {
  const [blockedTags, setBlockedTags] = useState<BlockedTag[]>([])

  const fetchBlockedTags = useCallback(async () => {
    const res = await apiFetch("/api/documents/blocked-tags")
    if (res.ok) {
      setBlockedTags(await res.json())
    }
  }, [])

  const blockTag = useCallback(async (tag: string): Promise<number> => {
    const res = await apiFetch("/api/documents/blocked-tags", {
      method: "POST",
      body: JSON.stringify({ tag }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Block failed" }))
      throw new Error(err.detail || "Block failed")
    }
    const data = await res.json()
    setBlockedTags(prev => [
      { id: crypto.randomUUID(), tag: data.tag, created_at: new Date().toISOString() },
      ...prev,
    ])
    return data.documents_updated
  }, [])

  const unblockTag = useCallback(async (tag: string) => {
    const res = await apiFetch(`/api/documents/blocked-tags/${encodeURIComponent(tag)}`, {
      method: "DELETE",
    })
    if (res.ok) {
      setBlockedTags(prev => prev.filter(bt => bt.tag !== tag))
    }
  }, [])

  useEffect(() => {
    fetchBlockedTags()
  }, [fetchBlockedTags])

  return { blockedTags, blockTag, unblockTag, fetchBlockedTags }
}
