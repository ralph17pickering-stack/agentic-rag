export interface Thread {
  id: string
  user_id: string
  title: string
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  thread_id: string
  user_id: string
  role: "user" | "assistant" | "system"
  content: string
  created_at: string
  web_results?: WebResult[] | null
}

export interface WebResult {
  title: string
  url: string
  snippet: string
}

export interface Document {
  id: string
  user_id: string
  filename: string
  storage_path: string
  file_type: string
  file_size: number
  status: "pending" | "processing" | "ready" | "error"
  error_message: string | null
  chunk_count: number
  content_hash: string | null
  is_duplicate?: boolean
  title: string | null
  summary: string | null
  topics: string[]
  document_date: string | null
  created_at: string
  updated_at: string
}
