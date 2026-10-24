import { useEffect, useState } from "react"
import { getJSON } from "../api"

const STAGES = {
  turn: "Full turn",
  stt: "Speech to text",
  tts: "Text to speech",
  llm: "Language model",
  "tool:search_knowledge_base": "Search",
  "tool:book_appointment": "Book appointment",
  "tool:lookup_order": "Order lookup",
}

export function Dashboard() {
  const [overview, setOverview] = useState(null)
  const [transcript, setTranscript] = useState(null)
  const [activeSession, setActiveSession] = useState(null)
  const [error, setError] = useState("")

  async function refresh() {
    setOverview(await getJSON("/api/admin/overview"))
  }

  useEffect(() => {
    refresh().catch((err) => setError(err.message))
  }, [])

  async function openSession(sessionId) {
    setActiveSession(sessionId)
    setTranscript(await getJSON(`/api/sessions/${sessionId}/messages`))
  }

  if (!overview) {
    return <section className="page">{error ? <p className="form-error">{error}</p> : <p>Loading the desk…</p>}</section>
  }

  const maxAvg = Math.max(...overview.latency.map((row) => row.avg_ms), 1)

  return (
    <section className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Operations</p>
          <h2>Dashboard</h2>
        </div>
        <button type="button" className="text-button" onClick={() => refresh().catch((err) => setError(err.message))}>
          Refresh
        </button>
      </header>
      {error && <p className="form-error">{error}</p>}
      <div className="stats">
        <Stat label="Documents" value={overview.counts.documents} />
        <Stat label="Chunks" value={overview.counts.chunks} />
        <Stat label="Sessions" value={overview.counts.sessions} />
        <Stat label="Tool calls" value={overview.counts.tool_calls} />
      </div>
      <div className="provider-line">
        <span>LLM {overview.providers.llm_provider}</span>
        <span>Embeddings {overview.providers.embedding_provider}</span>
        <span>STT {overview.providers.stt_provider}</span>
        <span>TTS {overview.providers.tts_provider}</span>
      </div>
      <div className="split">
        <section>
          <h3>Latency by stage</h3>
          {overview.latency.length === 0 && <p className="muted">No turns yet. Ask a question and come back.</p>}
          <div className="bars">
            {overview.latency.map((row) => (
              <div className="bar-row" key={row.stage}>
                <span>{STAGES[row.stage] || row.stage}</span>
                <div className="bar">
                  <div style={{ width: `${Math.max(6, (row.avg_ms / maxAvg) * 100)}%` }} />
                </div>
                <em>
                  {row.avg_ms} ms · p50 {row.p50_ms}
                </em>
              </div>
            ))}
          </div>
        </section>
        <section>
          <h3>Recent tool calls</h3>
          <ul className="plain">
            {overview.tool_calls.map((call) => (
              <li key={call.id}>
                <strong>{STAGES[`tool:${call.name}`] || call.name}</strong>
                <span>{call.summary}</span>
                <em>{call.latency_ms} ms</em>
              </li>
            ))}
            {overview.tool_calls.length === 0 && <li className="muted">None yet.</li>}
          </ul>
        </section>
      </div>
      <div className="split">
        <section>
          <h3>Appointments</h3>
          <ul className="plain">
            {overview.appointments.map((item) => (
              <li key={item.id}>
                <strong>{item.appointment_id}</strong>
                <span>
                  {item.name} · {item.date} {item.time}
                </span>
                <em>{item.reason}</em>
              </li>
            ))}
            {overview.appointments.length === 0 && <li className="muted">No appointments booked.</li>}
          </ul>
        </section>
        <section>
          <h3>Transcripts</h3>
          <ul className="plain">
            {overview.sessions.map((session) => (
              <li key={session.id}>
                <button type="button" className="linkish" onClick={() => openSession(session.id)}>
                  {session.title}
                </button>
                <span>{session.message_count} messages</span>
              </li>
            ))}
          </ul>
          {transcript && activeSession && (
            <div className="mini-transcript">
              {transcript.messages.map((message) => (
                <p key={message.id}>
                  <strong>{message.role}</strong> {message.content}
                </p>
              ))}
            </div>
          )}
        </section>
      </div>
      <p className="hint">Demo orders ORD-1001 through ORD-1004 live in the local SQLite database.</p>
    </section>
  )
}

function Stat({ label, value }) {
  return (
    <article className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  )
}
