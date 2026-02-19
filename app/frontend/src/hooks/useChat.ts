import { useState, useCallback } from "react"
import { apiFetch } from "@/lib/api"
import { supabase } from "@/lib/supabase"
import type { Message, WebResult, CitationSource } from "@/types"
import { formatToolStart, formatToolResult } from "@/lib/toolStatus"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8001"

export function useChat(threadId: string | null, onTitleUpdate?: (threadId: string, title: string) => void) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState("")
  const [loading, setLoading] = useState(false)
  const [webResults, setWebResults] = useState<WebResult[]>([])
  const [currentStatus, setCurrentStatus] = useState<string | null>(null)
  const [usedDeepAnalysis, setUsedDeepAnalysis] = useState(false)
  const [usedSources, setUsedSources] = useState<CitationSource[]>([])

  const fetchMessages = useCallback(async (tid: string) => {
    setLoading(true)
    try {
      const res = await apiFetch(`/api/threads/${tid}/messages`)
      if (res.ok) {
        const data: Message[] = await res.json()
        setMessages(data)
        // Restore web results from last assistant message that has them
        const lastWithResults = [...data].reverse().find(
          m => m.role === "assistant" && m.web_results && m.web_results.length > 0
        )
        setWebResults(lastWithResults?.web_results ?? [])
        const lastWithSources = [...data].reverse().find(
          m => m.role === "assistant" && m.used_sources && m.used_sources.length > 0
        )
        setUsedSources(lastWithSources?.used_sources ?? [])
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const sendMessage = useCallback(async (content: string, overrideThreadId?: string) => {
    const tid = overrideThreadId || threadId
    if (!tid || isStreaming) return

    // Optimistically add user message
    const tempUserMsg: Message = {
      id: crypto.randomUUID(),
      thread_id: tid,
      user_id: "",
      role: "user",
      content,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, tempUserMsg])
    setIsStreaming(true)
    setStreamingContent("")
    setWebResults([])
    setUsedSources([])
    setCurrentStatus(null)
    setUsedDeepAnalysis(false)

    try {
      const { data: { session } } = await supabase.auth.getSession()
      const response = await fetch(`${API_URL}/api/threads/${tid}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify({ content }),
      })

      if (!response.ok || !response.body) {
        throw new Error("Stream failed")
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      let fullContent = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() || ""

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith("data:")) continue
          const jsonStr = trimmed.slice(5).trim()
          if (!jsonStr) continue

          try {
            const data = JSON.parse(jsonStr)
            if (data.tool_start) {
              setCurrentStatus(formatToolStart(data.tool_start))
            }
            if (data.web_results) {
              const query: string = data.query ?? ""
              setWebResults(data.web_results)
              setCurrentStatus(formatToolResult("web_search", data.web_results.length, query))
            }
            if (data.used_sources) {
              const query: string = data.query ?? ""
              setUsedSources(prev => [...prev, ...data.used_sources])
              setCurrentStatus(formatToolResult("retrieve_documents", data.used_sources.length, query))
            }
            if (data.sub_agent_status) {
              if (data.sub_agent_status.done) {
                setCurrentStatus(null)
                setUsedDeepAnalysis(true)
              } else if (data.sub_agent_status.phase) {
                setCurrentStatus(data.sub_agent_status.phase)
                setUsedDeepAnalysis(true)
              }
            }
            if (data.done) {
              if (data.message) {
                setMessages(prev => [...prev, data.message])
                if (data.message?.used_sources) {
                  setUsedSources(data.message.used_sources)
                } else {
                  setUsedSources([])
                }
              }
              if (data.new_title && onTitleUpdate) {
                onTitleUpdate(tid, data.new_title)
              }
            } else if (data.token) {
              fullContent += data.token
              setStreamingContent(fullContent)
              // Clear status on first token — response has started
              if (fullContent.length === data.token.length) {
                setCurrentStatus(null)
              }
            }
          } catch {
            // Skip malformed JSON
          }
        }
      }
    } catch (error) {
      console.error("Chat error:", error)
    } finally {
      setIsStreaming(false)
      setStreamingContent("")
      setCurrentStatus(null)
    }
  }, [threadId, isStreaming, onTitleUpdate])

  const clearMessages = useCallback(async (tid: string) => {
    const res = await apiFetch(`/api/threads/${tid}/messages`, { method: "DELETE" })
    if (res.ok) {
      setMessages([])
    }
  }, [setMessages])

  return {
    messages,
    isStreaming,
    streamingContent,
    loading,
    webResults,
    currentStatus,
    usedDeepAnalysis,
    usedSources,
    fetchMessages,
    sendMessage,
    setMessages,
    clearMessages,
  }
}
