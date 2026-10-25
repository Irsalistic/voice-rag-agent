import { useEffect, useState } from "react"
import { getJSON, postJSON, readError } from "./api"
import { Chat } from "./components/Chat"
import { Dashboard } from "./components/Dashboard"
import { Documents } from "./components/Documents"

const VIEWS = [
  ["chat", "Chat"],
  ["documents", "Documents"],
  ["dashboard", "Dashboard"],
]

export default function App() {
  const [view, setView] = useState("chat")
  const [config, setConfig] = useState(null)
  const [sessions, setSessions] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [error, setError] = useState("")

  useEffect(() => {
    boot()
  }, [])

  async function boot() {
    try {
      setConfig(await getJSON("/api/health"))
      await refreshSessions(true)
    } catch (err) {
      setError(err.message || "The API is not reachable.")
    }
  }

  async function refreshSessions(selectFirst = false) {
    const data = await getJSON("/api/sessions")
    let rows = data.sessions
    if (rows.length === 0) {
      const created = await postJSON("/api/sessions")
      rows = [{ ...created, message_count: 0 }]
    }
    setSessions(rows)
    if (selectFirst || !rows.some((session) => session.id === sessionId)) {
      setSessionId(rows[0].id)
    }
  }

  async function newSession() {
    const created = await postJSON("/api/sessions")
    setSessions((prev) => [{ ...created, message_count: 0 }, ...prev])
    setSessionId(created.id)
    setView("chat")
  }

  async function removeSession(id) {
    const response = await fetch(`/api/sessions/${id}`, { method: "DELETE" })
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    const remaining = sessions.filter((session) => session.id !== id)
    setSessions(remaining)
    if (sessionId === id) {
      if (remaining.length === 0) await refreshSessions(true)
      else setSessionId(remaining[0].id)
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <strong>Vesper</strong>
            <em>Voice RAG agent</em>
          </div>
        </div>
        <div className="pills">
          {config && (
            <>
              <span>LLM · {config.llm_provider}</span>
              <span>Embeddings · {config.embedding_provider}</span>
              <span>
                Voice · {config.stt_provider === "none" ? "browser" : config.stt_provider} / {config.tts_provider}
              </span>
            </>
          )}
        </div>
      </header>
      {error && <p className="banner">{error}</p>}
      <div className="shell">
        <aside className="sidebar">
          <nav>
            {VIEWS.map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={view === id ? "active" : ""}
                onClick={() => setView(id)}
              >
                {label}
              </button>
            ))}
          </nav>
          {view === "chat" && (
            <div className="session-block">
              <div className="session-head">
                <span>Conversations</span>
                <button type="button" onClick={newSession}>
                  New
                </button>
              </div>
              <ul>
                {sessions.map((session) => (
                  <li key={session.id} className={session.id === sessionId ? "selected" : ""}>
                    <button type="button" onClick={() => setSessionId(session.id)}>
                      {session.title}
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Delete ${session.title}`}
                      onClick={() => removeSession(session.id)}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
        <main>
          {view === "chat" && sessionId && (
            <Chat
              key={sessionId}
              sessionId={sessionId}
              config={config}
              onSessionsChange={() => refreshSessions(false)}
            />
          )}
          {view === "chat" && !sessionId && !error && <p className="page">Opening a conversation…</p>}
          {view === "documents" && <Documents />}
          {view === "dashboard" && <Dashboard />}
        </main>
      </div>
    </div>
  )
}
