const MAX_QUERY_LEN = 60

function truncate(s: string): string {
  return s.length > MAX_QUERY_LEN ? s.slice(0, MAX_QUERY_LEN) + "\u2026" : s
}

export interface ToolStartData {
  tool: string
  query?: string
  question?: string
  mode?: string
  entity_a?: string
  entity_b?: string
}

export function formatToolStart(data: ToolStartData): string {
  const q = (s: string | undefined) => `"${truncate(s ?? "")}"`

  switch (data.tool) {
    case "retrieve_documents":
      return `Searching knowledge base for:\n${q(data.query)}`
    case "web_search":
      return `Searching the web for:\n${q(data.query)}`
    case "graph_search":
      if (data.mode === "relationship" && data.entity_a && data.entity_b) {
        return `Tracing relationship between:\n"${data.entity_a}" and "${data.entity_b}"`
      }
      return "Searching knowledge graph globally..."
    case "query_documents_metadata":
      return `Querying document metadata:\n${q(data.question)}`
    case "deep_analysis":
      return `Starting deep analysis:\n${q(data.query)}`
    default:
      return "Working..."
  }
}

export function formatToolResult(tool: string, count: number, query: string): string {
  switch (tool) {
    case "retrieve_documents":
      return query
        ? `Found ${count} chunk(s) for:\n"${truncate(query)}"`
        : `Found ${count} chunk(s)`
    case "web_search":
      return query
        ? `Found ${count} web result(s) for:\n"${truncate(query)}"`
        : `Found ${count} web result(s)`
    default:
      return `Found ${count} result(s)`
  }
}
