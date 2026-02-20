import { useEffect, useCallback } from "react"
import { useDocuments } from "@/hooks/useDocuments"
import { useBlockedTags } from "@/hooks/useBlockedTags"
import { DocumentsPanel } from "./DocumentsPanel"

export function DocumentsLayout() {
  const { documents, loading, uploading, fetchDocuments, uploadDocument, deleteDocument, updateDocument } =
    useDocuments()

  const { blockTag } = useBlockedTags()

  const handleBlockTag = useCallback(async (tag: string) => {
    const count = await blockTag(tag)
    fetchDocuments(true).catch(() => {})  // best-effort refresh; don't let it abort the caller
    return count
  }, [blockTag, fetchDocuments])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  return (
    <DocumentsPanel
      documents={documents}
      loading={loading}
      uploading={uploading}
      onUpload={uploadDocument}
      onDelete={deleteDocument}
      onUpdate={updateDocument}
      onBlockTag={handleBlockTag}
    />
  )
}
