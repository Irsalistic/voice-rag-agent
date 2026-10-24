import { useEffect, useRef, useState } from "react"
import { getJSON, readError } from "../api"
import { useVoice } from "../useVoice"

const PROMPTS = [
  "How many days do I have to return an item?",
  "Where is order ORD-1001?",
  "Book an appointment for Priya Shah, priya@example.com, on 2026-11-03 at 14:00 about a damaged lamp",
]

const TOOLS = {
  search_knowledge_base: "Searched documents",
  book_appointment: "Appointment",
  lookup_order: "Order lookup",
}

function rid() {
  return crypto.randomUUID()
}

export function Chat({ sessionId, config, onSessionsChange }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const scroller = useRef(null)
  const draftId = useRef(null)

  const voice = useVoice({
    sessionId,
    sttProvider: config?.stt_provider,
    mediaType: config?.tts_media_type,
    onEvent: applyVoiceEvent,
  })

  useEffect(() => {
    let cancel = false
    setMessages([])
    setError("")
    getJSON(`/api/sessions/${sessionId}/messages`)
      .then((data) => {
        if (!cancel) setMessages(data.messages)
      })
      .catch((err) => {
        if (!cancel) setError(err.message)
      })
    return () => {
      cancel = true
    }
  }, [sessionId])

  useEffect(() => {
    const node = scroller.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages, voice.interim])

  function patchDraft(mutate) {
    const id = draftId.current
    if (!id) return
    setMessages((prev) => prev.map((item) => (item.id === id ? mutate(item) : item)))
  }

  function applyEvent(event) {
    if (event.type === "token") {
      patchDraft((item) => ({ ...item, content: `${item.content}${event.text || ""}` }))
    } else if (event.type === "tool") {
      patchDraft((item) => ({ ...item, tools: [...(item.tools || []), event] }))
    } else if (event.type === "sources") {
      patchDraft((item) => ({ ...item, sources: event.sources || [] }))
    } else if (event.type === "notice") {
      patchDraft((item) => ({ ...item, notice: event.text }))
    } else if (event.type === "error") {
      setError(event.text)
    } else if (event.type === "done") {
      patchDraft((item) => ({ ...item, latency: event.latency_ms }))
    }
  }

  function applyVoiceEvent(event) {
    if (event.type === "transcript") {
      const assistantId = rid()
      draftId.current = assistantId
      setBusy(true)
      setMessages((prev) => [
        ...prev,
        { id: rid(), role: "user", content: event.text, sources: [], tools: [] },
        { id: assistantId, role: "assistant", content: "", sources: [], tools: [] },
      ])
      return
    }
    applyEvent(event)
    if (event.type === "done" || event.type === "error" || event.type === "interrupted") {
      setBusy(false)
      onSessionsChange?.()
    }
  }

  async function send(text) {
    const message = (text ?? input).trim()
    if (!message || busy) return
    setInput("")
    setError("")
    setBusy(true)
    const assistantId = rid()
    draftId.current = assistantId
    setMessages((prev) => [
      ...prev,
      { id: rid(), role: "user", content: message, sources: [], tools: [] },
      { id: assistantId, role: "assistant", content: "", sources: [], tools: [] },
    ])
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message }),
      })
      if (!response.ok || !response.body) throw new Error(await readError(response))
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split("\n\n")
        buffer = parts.pop() || ""
        for (const part of parts) {
          const line = part.split("\n").find((item) => item.startsWith("data:"))
          if (!line) continue
          applyEvent(JSON.parse(line.slice(5).trim()))
        }
      }
    } catch (err) {
      setError(err.message || "The request failed.")
    } finally {
      setBusy(false)
      onSessionsChange?.()
    }
  }

  const latestSources = [...messages].reverse().find((item) => item.sources?.length)?.sources || []

  return (
    <div className="chat-layout">
      <section className="conversation">
        <div className="transcript" ref={scroller}>
          {messages.length === 0 && (
            <div className="empty">
              <p className="eyebrow">Sample desk</p>
              <h2>Ask out loud, or type.</h2>
              <p>
                Harbor &amp; Co. policies are already loaded. Answers cite the passage they came
                from. Try an order id like ORD-1001, or book a support call.
              </p>
              <div className="prompts">
                {PROMPTS.map((prompt) => (
                  <button key={prompt} type="button" onClick={() => send(prompt)}>
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((message) => (
            <article key={message.id} className={`bubble ${message.role}`}>
              <span className="who">{message.role === "user" ? "You" : "Vesper"}</span>
              {message.notice && <p className="notice">{message.notice}</p>}
              {(message.tools || []).map((tool, index) => (
                <p key={`${message.id}-tool-${index}`} className="tool-pill">
                  {TOOLS[tool.name] || tool.name}
                  {tool.summary ? ` · ${tool.summary}` : ""}
                </p>
              ))}
              {message.content ? (
                <p className="body-text">{message.content}</p>
              ) : (
                message.role === "assistant" && busy && <p className="body-text waiting">Working through the tools…</p>
              )}
              {message.latency ? <p className="latency">{message.latency} ms</p> : null}
            </article>
          ))}
        </div>
        {error && <p className="form-error">{error}</p>}
        {voice.interim && <p className="interim">{voice.interim}</p>}
        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault()
            send()
          }}
        >
          <label className="sr-only" htmlFor="composer">
            Message
          </label>
          <textarea
            id="composer"
            value={input}
            rows={2}
            placeholder="Ask about a policy, an order, or book a call"
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                send()
              }
            }}
          />
          <div className="composer-actions">
            <button
              type="button"
              className={`mic phase-${voice.phase}`}
              onClick={voice.toggle}
              aria-pressed={voice.phase === "listening" || voice.phase === "speaking"}
              aria-label={voice.phase === "listening" ? "Stop listening" : "Talk"}
            >
              <span className="bars" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              {voice.label}
            </button>
            <label className="barge">
              <input
                type="checkbox"
                checked={voice.bargeIn}
                onChange={(event) => voice.setBargeIn(event.target.checked)}
              />
              Interrupt when I speak
            </label>
            <button className="send" type="submit" disabled={busy || !input.trim()}>
              Send
            </button>
          </div>
          {voice.error && <p className="form-error">{voice.error}</p>}
          <p className="hint">
            {voice.useBrowser
              ? "Speech recognition uses this browser. Headphones help if you interrupt the reply."
              : "Audio is transcribed on the server. Click the button again to stop, or speak over the reply."}
          </p>
        </form>
      </section>
      <aside className="sources">
        <h2>Sources</h2>
        {latestSources.length === 0 && <p className="muted">Citations for the latest answer land here.</p>}
        {latestSources.map((source) => (
          <article key={source.id || source.n} className="source-card">
            <header>
              <span>[{source.n}]</span>
              <strong>{source.source}</strong>
              {source.page ? <em>p. {source.page}</em> : null}
            </header>
            <p>{source.snippet}</p>
          </article>
        ))}
      </aside>
    </div>
  )
}
