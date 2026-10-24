import { useEffect, useState } from "react"
import { getJSON, readError } from "../api"

export function Documents() {
  const [documents, setDocuments] = useState([])
  const [openId, setOpenId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [dragOver, setDragOver] = useState(false)

  async function refresh() {
    const data = await getJSON("/api/documents")
    setDocuments(data.documents)
  }

  useEffect(() => {
    refresh().catch((err) => setError(err.message))
  }, [])

  async function upload(file) {
    if (!file) return
    setBusy(true)
    setError("")
    const body = new FormData()
    body.append("file", file)
    try {
      const response = await fetch("/api/documents", { method: "POST", body })
      if (!response.ok) throw new Error(await readError(response))
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function remove(documentId) {
    setError("")
    const response = await fetch(`/api/documents/${documentId}`, { method: "DELETE" })
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    if (openId === documentId) {
      setOpenId(null)
      setDetail(null)
    }
    await refresh()
  }

  async function open(documentId) {
    setOpenId(documentId)
    setDetail(null)
    try {
      setDetail(await getJSON(`/api/documents/${documentId}`))
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Knowledge base</p>
          <h2>Documents</h2>
        </div>
        <p className="lede">PDF, DOCX, TXT, and Markdown. Each file is chunked, embedded, and indexed for hybrid search.</p>
      </header>
      <label
        className={`dropzone ${dragOver ? "over" : ""}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragOver(false)
          upload(event.dataTransfer.files?.[0])
        }}
      >
        <input
          type="file"
          accept=".pdf,.docx,.txt,.md,.markdown,application/pdf,text/plain,text/markdown"
          onChange={(event) => {
            upload(event.target.files?.[0])
            event.target.value = ""
          }}
        />
        <strong>{busy ? "Indexing…" : "Drop a file, or browse"}</strong>
        <span>Up to 10 MB. Text is extracted locally.</span>
      </label>
      {error && <p className="form-error">{error}</p>}
      <ul className="doc-list">
        {documents.map((document) => (
          <li key={document.id}>
            <button type="button" className="doc-main" onClick={() => open(document.id)}>
              <strong>{document.filename}</strong>
              <span>
                {document.chunk_count} chunks · {formatBytes(document.byte_size)}
              </span>
            </button>
            <button type="button" className="text-button" onClick={() => remove(document.id)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
      {detail && openId === detail.id && (
        <div className="chunk-list">
          <h3>{detail.filename}</h3>
          {detail.chunks.map((chunk) => (
            <article key={chunk.id}>
              <span>
                Chunk {chunk.ordinal + 1}
                {chunk.page ? ` · page ${chunk.page}` : ""}
              </span>
              <p>{chunk.snippet}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

function formatBytes(size) {
  if (!size) return "0 B"
  if (size < 1024) return `${size} B`
  return `${(size / 1024).toFixed(1)} KB`
}
