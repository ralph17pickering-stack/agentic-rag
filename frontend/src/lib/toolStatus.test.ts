import { describe, it, expect } from "vitest"
import { formatToolStart, formatToolResult } from "./toolStatus"

describe("formatToolStart", () => {
  it("retrieve_documents with query", () => {
    expect(formatToolStart({ tool: "retrieve_documents", query: "revenue figures Q3" }))
      .toBe('Searching knowledge base for:\n"revenue figures Q3"')
  })

  it("retrieve_documents truncates long query", () => {
    const long = "a".repeat(80)
    const result = formatToolStart({ tool: "retrieve_documents", query: long })
    expect(result).toContain("Searching knowledge base for:")
    expect(result.split("\n")[1].length).toBeLessThanOrEqual(63) // 60 chars + quotes + ellipsis
  })

  it("web_search with query", () => {
    expect(formatToolStart({ tool: "web_search", query: "latest AI benchmarks" }))
      .toBe('Searching the web for:\n"latest AI benchmarks"')
  })

  it("graph_search global mode", () => {
    expect(formatToolStart({ tool: "graph_search", mode: "global" }))
      .toBe("Searching knowledge graph globally...")
  })

  it("graph_search relationship mode", () => {
    expect(formatToolStart({ tool: "graph_search", mode: "relationship", entity_a: "OpenAI", entity_b: "Microsoft" }))
      .toBe('Tracing relationship between:\n"OpenAI" and "Microsoft"')
  })

  it("query_documents_metadata", () => {
    expect(formatToolStart({ tool: "query_documents_metadata", question: "how many PDFs?" }))
      .toBe('Querying document metadata:\n"how many PDFs?"')
  })

  it("deep_analysis", () => {
    expect(formatToolStart({ tool: "deep_analysis", query: "compare revenue trends" }))
      .toBe('Starting deep analysis:\n"compare revenue trends"')
  })

  it("unknown tool", () => {
    expect(formatToolStart({ tool: "unknown_tool" })).toBe("Working...")
  })
})

describe("formatToolResult", () => {
  it("retrieve_documents with results and query", () => {
    expect(formatToolResult("retrieve_documents", 5, "revenue Q3"))
      .toBe('Found 5 chunk(s) for:\n"revenue Q3"')
  })

  it("retrieve_documents with no query", () => {
    expect(formatToolResult("retrieve_documents", 3, ""))
      .toBe("Found 3 chunk(s)")
  })

  it("web_results with query", () => {
    expect(formatToolResult("web_search", 4, "AI news"))
      .toBe('Found 4 web result(s) for:\n"AI news"')
  })
})
