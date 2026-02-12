import { useState, useCallback } from "react"
import { apiFetch } from "@/lib/api"
import { supabase } from "@/lib/supabase"
import type { Message, WebResult } from "@/types"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8001"

export function useChat(threadId: string | null, onTitleUpdate?: (threadId: string, title: string) => void) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState("")
  const [loading, setLoading] = useState(false)
  const [webResults, setWebResults] = useState<WebResult[]>([])
  const [deepAnalysisPhase, setDeepAnalysisPhase] = useState<string | null>(null)
  const [usedDeepAnalysis, setUsedDeepAnalysis] = useState(false)

  const fetchMessages = useCallback(async (tid: string) => {
    setLoading(true)
    try {
      const res = await apiFetch(`/api/threads/${tid}/messages`)
      if (res.ok) {
        const data = await res.json()
        setMessages(data)
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
    setDeepAnalysisPhase(null)
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
            if (data.web_results) {
              setWebResults(data.web_results)
            }
            if (data.sub_agent_status) {
              if (data.sub_agent_status.done) {
                setDeepAnalysisPhase(null)
                setUsedDeepAnalysis(true)
              } else if (data.sub_agent_status.phase) {
                setDeepAnalysisPhase(data.sub_agent_status.phase)
                setUsedDeepAnalysis(true)
              }
            }
            if (data.done) {
              // Final event with saved message
              if (data.message) {
                setMessages(prev => [...prev, data.message])
              }
              if (data.new_title && onTitleUpdate) {
                onTitleUpdate(tid, data.new_title)
              }
            } else if (data.token) {
              fullContent += data.token
              setStreamingContent(fullContent)
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
      setDeepAnalysisPhase(null)
    }
  }, [threadId, isStreaming, onTitleUpdate])

  return {
    messages,
    isStreaming,
    streamingContent,
    loading,
    webResults,
    deepAnalysisPhase,
    usedDeepAnalysis,
    fetchMessages,
    sendMessage,
    setMessages,
  }
}
