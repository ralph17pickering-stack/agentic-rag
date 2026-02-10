import { supabase } from "./supabase"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8001"

export async function apiFetch(path: string, options: RequestInit = {}) {
  const { data: { session } } = await supabase.auth.getSession()
  const headers = new Headers(options.headers)
  if (session?.access_token) {
    headers.set("Authorization", `Bearer ${session.access_token}`)
  }
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }
  return fetch(`${API_URL}${path}`, { ...options, headers })
}
