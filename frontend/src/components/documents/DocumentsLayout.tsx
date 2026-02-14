import { useEffect } from "react"
import { useDocuments } from "@/hooks/useDocuments"
import { DocumentsPanel } from "./DocumentsPanel"

export function DocumentsLayout() {
  const { documents, loading, uploading, fetchDocuments, uploadDocument, deleteDocument, updateDocument } =
    useDocuments()

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
    />
  )
}
