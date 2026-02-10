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
  created_at: string
  updated_at: string
}
