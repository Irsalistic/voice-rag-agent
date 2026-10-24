import { useEffect, useRef, useState } from "react"

export function useVoice({ sessionId, sttProvider, mediaType, onEvent }) {
  const wsRef = useRef(null)
  const recRef = useRef(null)
  const streamRef = useRef(null)
  const recogRef = useRef(null)
  const audioRef = useRef(null)
  const genRef = useRef(0)
  const queueRef = useRef(Promise.resolve())
  const onEventRef = useRef(onEvent)
  const sessionRef = useRef(sessionId)
  const [phase, setPhase] = useState("idle")
  const [error, setError] = useState("")
  const [interim, setInterim] = useState("")
  const [bargeIn, setBargeIn] = useState(true)
  const phaseRef = useRef("idle")
  const bargeRef = useRef(true)

  onEventRef.current = onEvent
  sessionRef.current = sessionId
  phaseRef.current = phase
  bargeRef.current = bargeIn

  const browserSpeech =
    typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition)
  const useBrowser = !sttProvider || sttProvider === "none"

  useEffect(() => {
    return () => {
      wsRef.current?.close()
      stopTracks()
    }
  }, [sessionId])

  useEffect(() => {
    if (phase !== "speaking" || !bargeIn || !streamRef.current) return undefined
    const stream = streamRef.current
    const context = new AudioContext()
    const source = context.createMediaStreamSource(stream)
    const analyser = context.createAnalyser()
    analyser.fftSize = 512
    source.connect(analyser)
    const data = new Uint8Array(analyser.fftSize)
    const started = performance.now()
    let hot = 0
    let frame = 0
    let stopped = false
    const tick = () => {
      if (stopped) return
      analyser.getByteTimeDomainData(data)
      let sum = 0
      for (const value of data) {
        const centered = (value - 128) / 128
        sum += centered * centered
      }
      const rms = Math.sqrt(sum / data.length)
      if (performance.now() - started > 400 && rms > 0.14) hot += 1
      else hot = 0
      if (hot >= 8) {
        interruptAndListen()
        return
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => {
      stopped = true
      cancelAnimationFrame(frame)
      context.close()
    }
  }, [phase, bargeIn])

  function socketUrl() {
    const proto = window.location.protocol === "https:" ? "wss" : "ws"
    return `${proto}://${window.location.host}/api/voice/ws`
  }

  function connect() {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      return Promise.resolve(wsRef.current)
    }
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(socketUrl())
      socket.binaryType = "arraybuffer"
      socket.onopen = () => {
        socket.send(JSON.stringify({ type: "start", session_id: sessionRef.current }))
      }
      socket.onmessage = (event) => {
        if (typeof event.data !== "string") {
          enqueueAudio(event.data)
          setPhase("speaking")
          return
        }
        let message
        try {
          message = JSON.parse(event.data)
        } catch {
          return
        }
        if (message.type === "ready") resolve(socket)
        if (message.type === "interrupted") stopPlayback()
        if (message.type === "done" || message.type === "error") {
          queueRef.current.then(() => {
            if (phaseRef.current !== "listening") setPhase("idle")
          })
        }
        onEventRef.current?.(message)
      }
      socket.onerror = () => {
        setError("The voice connection failed.")
        setPhase("idle")
        reject(new Error("socket"))
      }
      socket.onclose = () => {
        if (wsRef.current === socket) wsRef.current = null
      }
      wsRef.current = socket
    })
  }

  function enqueueAudio(buffer) {
    const generation = genRef.current
    const mime = mediaType || "audio/mpeg"
    queueRef.current = queueRef.current.then(
      () =>
        new Promise((resolve) => {
          if (generation !== genRef.current) {
            resolve()
            return
          }
          const url = URL.createObjectURL(new Blob([buffer], { type: mime }))
          const audio = new Audio(url)
          audioRef.current = audio
          const finish = () => {
            URL.revokeObjectURL(url)
            resolve()
          }
          audio.onended = finish
          audio.onerror = finish
          audio.play().catch(finish)
        }),
    )
  }

  function stopPlayback() {
    genRef.current += 1
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    queueRef.current = Promise.resolve()
  }

  function stopTracks() {
    recRef.current?.stop?.()
    recogRef.current?.stop?.()
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }

  async function startRecorder() {
    const stream =
      streamRef.current ||
      (await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      }))
    streamRef.current = stream
    const recorder = new MediaRecorder(stream)
    recorder.ondataavailable = async (event) => {
      if (event.data.size && wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(await event.data.arrayBuffer())
      }
    }
    recorder.onstop = () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({ type: "utterance_end", mime: recorder.mimeType || "audio/webm" }),
        )
      }
      setPhase("thinking")
    }
    recorder.start(250)
    recRef.current = recorder
    setPhase("listening")
  }

  function startRecognition() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition
    const recognition = new Recognition()
    recognition.continuous = false
    recognition.interimResults = true
    recognition.lang = "en-US"
    recognition.onresult = (event) => {
      let finalText = ""
      let pending = ""
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const piece = event.results[index][0].transcript
        if (event.results[index].isFinal) finalText += piece
        else pending += piece
      }
      setInterim(pending)
      if (finalText.trim() && wsRef.current?.readyState === WebSocket.OPEN) {
        setInterim("")
        setPhase("thinking")
        wsRef.current.send(JSON.stringify({ type: "text", text: finalText.trim() }))
      }
    }
    recognition.onerror = () => {
      setError("Speech recognition stopped. You can keep typing.")
      setPhase("idle")
    }
    recognition.onend = () => {
      if (phaseRef.current === "listening") setPhase("idle")
    }
    recognition.start()
    recogRef.current = recognition
    setPhase("listening")
  }

  async function listen() {
    setError("")
    setPhase("connecting")
    try {
      await connect()
    } catch {
      setPhase("idle")
      return
    }
    if (useBrowser) {
      if (!browserSpeech) {
        setError("This browser has no speech recognition. Type instead, or configure Whisper.")
        setPhase("idle")
        return
      }
      startRecognition()
      return
    }
    try {
      await startRecorder()
    } catch {
      setError("Microphone permission was blocked.")
      setPhase("idle")
    }
  }

  function interruptAndListen() {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "barge_in" }))
    }
    stopPlayback()
    recogRef.current?.stop()
    if (recRef.current && recRef.current.state === "recording") {
      recRef.current.stop()
      return
    }
    listen()
  }

  async function toggle() {
    if (phase === "listening") {
      if (recRef.current && recRef.current.state === "recording") recRef.current.stop()
      else recogRef.current?.stop()
      setInterim("")
      return
    }
    if (phase === "speaking" || phase === "thinking") {
      interruptAndListen()
      return
    }
    await listen()
  }

  const label =
    phase === "listening"
      ? "Listening"
      : phase === "thinking"
        ? "Thinking"
        : phase === "speaking"
          ? "Speaking"
          : phase === "connecting"
            ? "Connecting"
            : "Talk"

  return { phase, error, interim, bargeIn, setBargeIn, toggle, label, useBrowser }
}
