// src/components/AgentStream.jsx
"use client"

import React, { useEffect, useMemo, useRef, useState } from "react"
import { getMessaging, onMessage, isSupported } from "firebase/messaging"
import { app } from "../lib/firebase"
import { ensureFreshFcmToken, refreshFcmToken } from "../lib/fcm-token"

import { API_BASE, MAPS_BROWSER_KEY } from "../config"
import { buildRunUrl } from "../utils/api"

/* ──────────────── UI helpers ──────────────── */
const Pill = ({ children, tone = "neutral" }) => {
  const cls =
    tone === "ok"
      ? "bg-emerald-900/40 text-emerald-300 border-emerald-800"
      : tone === "warn"
      ? "bg-amber-900/40 text-amber-300 border-amber-800"
      : tone === "err"
      ? "bg-rose-900/40 text-rose-300 border-rose-800"
      : "bg-slate-800/60 text-slate-300 border-slate-700"
  return <span className={`pill border ${cls}`}>{children}</span>
}
const K = ({ children }) => <span className="text-gray-400">{children}</span>

function PrettyObject({ data }) {
  if (data == null) return <div className="text-gray-400">—</div>
  if (typeof data !== "object") return <div className="text-gray-200 break-words">{String(data)}</div>

  if (Array.isArray(data)) {
    if (data.length === 0) return <div className="text-gray-400">[]</div>
    return (
      <ul className="space-y-1">
        {data.map((item, i) => (
          <li key={i} className="rounded-lg bg-black/20 border border-[var(--grab-edge)] p-2">
            <PrettyObject data={item} />
          </li>
        ))}
      </ul>
    )
  }

  const entries = Object.entries(data)
  if (entries.length === 0) return <div className="text-gray-400">{`{}`}</div>

  return (
    <dl className="grid sm:grid-cols-2 gap-x-4 gap-y-2">
      {entries.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-xs uppercase tracking-wider text-gray-400">{k}</dt>
          <dd className="text-gray-200">
            <PrettyObject data={v} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

/* ──────────────── Google Maps JS loader (top “Live Map”) ──────────────── */
const loadGoogleMaps = (() => {
  let promise
  return () => {
    if (typeof window === "undefined") return Promise.reject(new Error("No window"))
    if (window.google?.maps?.importLibrary || window.google?.maps) return Promise.resolve(window.google.maps)
    if (promise) return promise

    const key = MAPS_BROWSER_KEY || window.__GMAPS_KEY
    if (!key) return Promise.reject(new Error("Missing Google Maps browser key"))

    const url = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(
      key
    )}&v=weekly&loading=async&libraries=geometry,places,marker`
    promise = new Promise((resolve, reject) => {
      const s = document.createElement("script")
      s.src = url
      s.async = true
      s.defer = true
      s.onload = () => (window.google?.maps ? resolve(window.google.maps) : reject(new Error("Maps undefined")))
      s.onerror = () => reject(new Error("Failed to load Maps JS API"))
      document.head.appendChild(s)
    })
    return promise
  }
})()

const decodePolylineFallback = (str) => {
  let i = 0,
    lat = 0,
    lng = 0,
    pts = []
  while (i < str.length) {
    let b,
      shift = 0,
      res = 0
    do {
      b = str.charCodeAt(i++) - 63
      res |= (b & 0x1f) << shift
      shift += 5
    } while (b >= 0x20)
    const dlat = res & 1 ? ~(res >> 1) : res >> 1
    lat += dlat
    shift = 0
    res = 0
    do {
      b = str.charCodeAt(i++) - 63
      res |= (b & 0x1f) << shift
      shift += 5
    } while (b >= 0x20)
    const dlng = res & 1 ? ~(res >> 1) : res >> 1
    lng += dlng
    pts.push({ lat: lat / 1e5, lng: lng / 1e5 })
  }
  return pts
}

/* ──────────────── Lightweight “Live Map” panel ──────────────── */
function MapBox({ payload }) {
  const divRef = useRef(null)
  const mapRef = useRef(null)
  const overlaysRef = useRef([])

  useEffect(() => {
    let cancel = false
    ;(async () => {
      const maps = await loadGoogleMaps()
      if (cancel || !divRef.current) return

      const { Map } = maps.importLibrary ? await maps.importLibrary("maps") : maps
      if (!mapRef.current) {
        mapRef.current = new Map(divRef.current, {
          center: { lat: 12.9716, lng: 77.5946 },
          zoom: 12,
          gestureHandling: "greedy",
        })
      }
      render(maps)
    })().catch((e) => console.warn("[MapBox]", e))
    return () => {
      cancel = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload])

  const clear = () => {
    overlaysRef.current.forEach((o) => o?.setMap?.(null))
    overlaysRef.current = []
  }

  const fit = (maps, b) => {
    if (!b || !mapRef.current) return
    const LLB = maps.LatLngBounds || window.google.maps.LatLngBounds
    mapRef.current.fitBounds(
      new LLB(new maps.LatLng(b.south, b.west), new maps.LatLng(b.north, b.east)),
      32
    )
  }

  const decode = (maps, enc) =>
    maps.geometry?.encoding?.decodePath ? maps.geometry.encoding.decodePath(enc) : decodePolylineFallback(enc)

  const render = (maps) => {
    if (!payload || !mapRef.current) return
    clear()

    if (payload.kind === "directions") {
      payload.routes?.forEach((r, i) => {
        if (!r.polyline) return
        const p = new window.google.maps.Polyline({
          path: decode(maps, r.polyline),
          strokeOpacity: i ? 0.6 : 0.95,
          strokeWeight: i ? 4 : 6,
        })
        p.setMap(mapRef.current)
        overlaysRef.current.push(p)
      })
      fit(maps, payload.bounds)
    }

    if (payload.kind === "markers") {
      payload.markers?.forEach((m) => {
        const Adv = window.google?.maps?.marker?.AdvancedMarkerElement
        const mk = Adv
          ? new Adv({ map: mapRef.current, position: m.position, title: m.title })
          : new window.google.maps.Marker({ map: mapRef.current, position: m.position, title: m.title })
        overlaysRef.current.push(mk)
      })
      fit(maps, payload.bounds)
    }

    if (payload.kind === "compare_routes") {
      const base = payload.baseline?.polyline
      const cand = payload.candidate?.polyline
      if (base) {
        overlaysRef.current.push(
          new window.google.maps.Polyline({
            path: decode(maps, base),
            strokeOpacity: 0.4,
            strokeWeight: 5,
            map: mapRef.current,
          })
        )
      }
      if (cand) {
        overlaysRef.current.push(
          new window.google.maps.Polyline({
            path: decode(maps, cand),
            strokeWeight: 6,
            map: mapRef.current,
          })
        )
      }
      fit(maps, payload.bounds)
    }
  }

  return <div ref={divRef} className="h-96 w-full rounded-2xl border border-[var(--grab-edge)] bg-black/20" />
}

/* ──────────────── Per-step Google Maps Embed ──────────────── */
const StepEmbedMap = ({ step }) => {
  const url = step?.observation?.map?.embedUrl
  if (!url) return null
  return (
    <div className="h-72 w-full rounded-xl overflow-hidden border border-[var(--grab-edge)]">
      <iframe
        title="Google Directions"
        src={url}
        width="100%"
        height="100%"
        style={{ border: 0 }}
        loading="lazy"
        allowFullScreen
        referrerPolicy="no-referrer-when-downgrade"
      />
    </div>
  )
}

/* ──────────────── Step card ──────────────── */
function StepItem({ step, index, active = false, complete = false }) {
  const [open, setOpen] = useState(true)
  const ok = step.passed === true

  const strip = (o) => {
    if (!o || typeof o !== "object") return o
    if (Array.isArray(o)) return o.map(strip)
    const c = { ...o }
    ;["options", "awaiting", "session_id", "map"].forEach((k) => delete c[k])
    return c
  }

  return (
    <div id={`step-${index}`} className="relative pl-6" style={{ animation: `fadeInUp 400ms ease ${index * 80}ms both` }}>
      {/* dot + connector */}
      <div className="absolute left-0 top-2">
        <div
          className={`w-3 h-3 rounded-full ${ok ? "bg-emerald-400" : "bg-rose-400"} ring-4 ring-[var(--grab-bg)] ${
            active ? "timeline-dot-active" : ""
          }`}
        />
      </div>
      {index !== 0 && <div className={`absolute left-1 top-[-24px] bottom-6 w-[2px] ${complete ? "conn-complete" : "conn-upcoming"}`} />}

      <div className={`card p-4 ${active ? "step-active" : ""}`}>
        {/* header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Pill>Step {typeof step.index === "number" ? step.index + 1 : "—"}</Pill>
            <div className="font-semibold text-white">{step.intent || "—"}</div>
          </div>
          <div className="flex items-center gap-2">
            <Pill tone={ok ? "ok" : "err"}>{ok ? "passed" : "failed"}</Pill>
            <button className="btn btn-ghost" onClick={() => setOpen((v) => !v)}>
              {open ? "Hide" : "Show"}
            </button>
          </div>
        </div>

        {/* meta */}
        <div className="grid md:grid-cols-3 gap-4">
          <div><K>Tool</K><div className="font-medium text-[var(--grab-green)]">{step.tool}</div></div>
          <div><K>Assertion</K><div className="font-medium break-words">{step.assertion || "—"}</div></div>
          <div><K>Timestamp</K><div className="font-medium">{step.ts || "—"}</div></div>
        </div>

        {/* params / obs */}
        {open && (
          <div className="mt-4 grid md:grid-cols-2 gap-4">
            <div><K>Params</K><PrettyObject data={strip(step.params)} /></div>
            <div><K>Observation</K><PrettyObject data={strip(step.observation)} /></div>
          </div>
        )}

        {/* Google Maps iframe */}
        {step?.observation?.map?.kind === "directions" && (
          <div className="mt-4">
            <StepEmbedMap step={step} />
          </div>
        )}
      </div>
    </div>
  )
}

/* ──────────────── View toggle ──────────────── */
const ViewToggle = ({ mode, setMode }) => {
  const isGUI = mode === "gui"
  return (
    <div className="w-[220px] rounded-full border border-[var(--grab-edge)] bg-black/20 p-1 relative select-none">
      <div
        className={`absolute top-1 bottom-1 w-[108px] rounded-full transition-transform ${
          isGUI ? "translate-x-1" : "translate-x-[109px]"
        }`}
        style={{ background: "linear-gradient(90deg,#0c1511,#14231c)" }}
      />
      <div className="relative z-10 grid grid-cols-2 text-xs font-medium">
        <button className={`py-1.5 ${isGUI ? "text-white" : "text-gray-400"}`} onClick={() => setMode("gui")}>
          GUI Chain
        </button>
        <button className={`py-1.5 ${!isGUI ? "text-white" : "text-gray-400"}`} onClick={() => setMode("cli")}>
          CLI Chain
        </button>
      </div>
    </div>
  )
}

/* fade-in keyframes */
if (!document.getElementById("fadeInUpKeyframes")) {
  const st = document.createElement("style")
  st.id = "fadeInUpKeyframes"
  st.textContent = "@keyframes fadeInUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}"
  document.head.appendChild(st)
}

/* ------------ Helper for image clarify (unchanged) ------------ */
function ImageAnswer({ onSubmit }) {
  const [files, setFiles] = useState(null)
  const [busy, setBusy] = useState(false)
  return (
    <div className="flex flex-col gap-2">
      <input type="file" accept="image/*" multiple onChange={(e) => setFiles(e.target.files)} className="input" />
      <button
        className="btn btn-primary"
        disabled={busy || !files || files.length === 0}
        onClick={async () => {
          setBusy(true)
          try {
            await onSubmit(files)
          } finally {
            setBusy(false)
          }
        }}
      >
        {busy ? "Uploading…" : "Upload & Continue"}
      </button>
      <div className="text-xs text-gray-500">Tip: include the seal, any spillage, and the outer bag.</div>
    </div>
  )
}

/* ──────────────── Main component ──────────────── */
export default function AgentStream({ scenarioText }) {
  /* ── state ── */
  const [events, setEvents] = useState([])
  const [rawLines, setRawLines] = useState([])
  const [status, setStatus] = useState("idle")
  const [error, setError] = useState("")
  const [mode, setMode] = useState("gui")
  const [activeIndex, setActiveIndex] = useState(-1)
  const [isPlaying, setIsPlaying] = useState(false)
  const [followLive, setFollowLive] = useState(true)
  const esRef = useRef(null)

  // clarify
  const [sessionId, setSessionId] = useState("")
  const [clarify, setClarify] = useState(null)
  const [answerDraft, setAnswerDraft] = useState("")

  // FCM
  const [fcmSupported, setFcmSupported] = useState(false)
  const [fcmToken, setFcmToken] = useState("")
  const [notifPermission, setNotifPermission] = useState(Notification?.permission ?? "default")

  const previewUrl = scenarioText
    ? `${API_BASE}/api/agent/run?${new URLSearchParams({ scenario: scenarioText }).toString()}`
    : ""

  /* ── push bootstrap ── */
  useEffect(() => {
    let off = () => {}
    ;(async () => {
      const supported = await isSupported()
      setFcmSupported(supported)
      if (!supported) return

      const reg =
        (await navigator.serviceWorker.getRegistration()) ||
        (await navigator.serviceWorker.register("/firebase-messaging-sw.js"))

      const messaging = getMessaging(app)
      off = onMessage(messaging, async (payload) => {
        if (Notification.permission === "granted") {
          const title = payload?.notification?.title || "Notification"
          const body = payload?.notification?.body || ""
          const data = payload?.data || {}
          const swr = (await navigator.serviceWorker.getRegistration()) || reg
          swr?.showNotification(title, { body, data, tag: payload?.messageId, requireInteraction: true })
        }
      })
    })()
    return () => off()
  }, [])

  useEffect(() => {
    if (Notification?.permission === "granted") ensureFreshFcmToken().then((t) => t && setFcmToken(t))
  }, [])

  /* ── SSE helpers ── */
  const closeStream = () => {
    try {
      esRef.current?.close?.()
    } catch {}
    esRef.current = null
  }

  const handleSSELine = async (line) => {
    setRawLines((p) => [...p, line])
    if (!line) return
    if (line === "[DONE]") {
      setStatus("done")
      closeStream()
      setFollowLive(false)
      return
    }

    try {
      const payload = JSON.parse(line)

      // session id
      if (payload?.type === "session" && payload?.data?.session_id) setSessionId(payload.data.session_id)
      if (payload?.type === "clarify" && payload?.data?.session_id) setSessionId(payload.data.session_id)

      // auto-rotate FCM token on UNREGISTERED
      const err = payload?.data?.observation?.error
      const errCode =
        err?.errorCode ||
        (typeof err === "object" && JSON.stringify(err).includes('"UNREGISTERED"') ? "UNREGISTERED" : null)
      if (errCode === "UNREGISTERED") {
        const t = await refreshFcmToken()
        if (t) setFcmToken(t)
      }

      // clarify panel
      if (payload?.type === "clarify") {
        setClarify(payload.data || null)
        setStatus("awaiting")
      }

      setEvents((p) => [...p, payload])
    } catch {
      /* ignore ping */
    }
  }

  const wireSSE = (url) => {
    const es = new EventSource(url)
    esRef.current = es
    es.onmessage = (e) => handleSSELine(e.data)
    es.onerror = () => {
      setStatus("error")
      setError("Stream error. Check backend, CORS, token.")
      closeStream()
    }
  }

  /* ── start / stop ── */
  const start = async () => {
    if (!scenarioText) return
    closeStream()
    setActiveIndex(-1)
    setIsPlaying(false)
    setFollowLive(true)
    setEvents([])
    setRawLines([])
    setError("")
    setClarify(null)
    setSessionId("")
    setStatus("streaming")

    try {
      if (Notification && Notification.permission !== "granted") {
        const perm = await Notification.requestPermission()
        setNotifPermission(perm)
        if (perm !== "granted") {
          setStatus("error")
          setError("Enable notifications to receive FCM pushes.")
          return
        }
      }

      const liveTok = (await ensureFreshFcmToken()) || fcmToken
      if (!liveTok) {
        setStatus("error")
        setError("Could not obtain FCM token.")
        return
      }
      if (liveTok !== fcmToken) setFcmToken(liveTok)

      const url = await buildRunUrl({
        scenario: scenarioText,
        passenger_token: liveTok,
        customer_token: liveTok,
        driver_token: liveTok,
      })
      wireSSE(url)
    } catch (e) {
      setStatus("error")
      setError(e.message || "Failed to start stream")
    }
  }

  const stop = () => {
    closeStream()
    setStatus("done")
    setIsPlaying(false)
    setFollowLive(false)
  }

  const resumeWithAnswer = async (answer) => {
    if (!sessionId) return setError("Missing session id")

    closeStream()
    setStatus("streaming")
    try {
      const liveTok = fcmToken || (await ensureFreshFcmToken())
      if (liveTok && liveTok !== fcmToken) setFcmToken(liveTok)

      const ans = clarify?.question_id ? { [clarify.question_id]: answer } : {}
      setClarify(null)
      setAnswerDraft("")

      const qs = new URLSearchParams()
      qs.set("session_id", sessionId)
      qs.set("answers", JSON.stringify(ans))
      if (liveTok) {
        qs.set("passenger_token", liveTok)
        qs.set("customer_token", liveTok)
      }
      wireSSE(`${API_BASE}/api/agent/run?${qs}`)
    } catch (e) {
      setStatus("error")
      setError(e.message || "Failed to resume")
    }
  }

  /* ── derive data ── */
  const classification = useMemo(() => events.find((e) => e.type === "classification")?.data, [events])
  const steps = useMemo(() => events.filter((e) => e.type === "step").map((e) => ({ ...e.data, ts: e.at })), [events])
  const summaryEvt = useMemo(() => events.find((e) => e.type === "summary")?.data, [events])

  // live map payload (most recent)
  const mapPayload = useMemo(() => {
    if (!steps.length) return null
    let idx = activeIndex >= 0 ? activeIndex : steps.length - 1
    for (let i = idx; i >= 0; i--) {
      const m = steps[i]?.observation?.map
      if (m) return m
    }
    return null
  }, [steps, activeIndex])

  const summaryText = useMemo(() => {
    if (!summaryEvt) return ""
    const msg = summaryEvt.message || summaryEvt.summary
    if (msg && String(msg).trim()) return msg
    const kind = classification?.kind
    const sev = classification?.severity
    const stepsCount = summaryEvt?.metrics?.steps
    const outcome = summaryEvt?.outcome
    const lastMsg = steps.length ? steps.at(-1)?.final_message || steps.at(-1)?.finalMessage : ""
    const bits = []
    if (outcome) bits.push(`Outcome: ${outcome}`)
    if (typeof stepsCount === "number") bits.push(`${stepsCount} step${stepsCount === 1 ? "" : "s"}`)
    if (kind) bits.push(`Kind: ${kind}${sev ? ` (${sev})` : ""}`)
    if (lastMsg) bits.push(lastMsg)
    return bits.join(" • ")
  }, [summaryEvt, classification, steps])

  /* follow-live / play-through */
  useEffect(() => {
    if (followLive && steps.length) setActiveIndex(steps.length - 1)
  }, [steps.length, followLive])
  useEffect(() => {
    if (!isPlaying) return
    const id = setInterval(() => setActiveIndex((i) => Math.min((i ?? -1) + 1, steps.length - 1)), 900)
    return () => clearInterval(id)
  }, [isPlaying, steps.length])
  useEffect(() => {
    if (activeIndex < 0) return
    const el = document.getElementById(`step-${activeIndex}`)
    el?.scrollIntoView({ behavior: "smooth", block: "center" })
  }, [activeIndex])

  /* ───────────── GUI view ───────────── */
  const GUIView = (
    <div className="space-y-6">
      {/* push status */}
      <div className="card p-4 flex items-center justify-between gap-4">
        <div className="text-sm">
          <div className="font-medium mb-1">Push Delivery</div>
          <div className="text-gray-400">
            {fcmSupported ? "Web Push is supported" : "Web Push not supported"}{" • "}
            Permission: <strong>{notifPermission}</strong>
            {fcmToken && (
              <>
                {" • "} Token:{" "}
                <code className="text-xs">
                  {fcmToken.slice(0, 12)}…{fcmToken.slice(-8)}
                </code>
              </>
            )}
          </div>
        </div>
      </div>

      {/* live map */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm uppercase tracking-wider text-gray-400">Map</div>
          <Pill tone={mapPayload ? "ok" : "warn"}>{mapPayload ? "live" : "no data"}</Pill>
        </div>
        {mapPayload ? (
          <MapBox payload={mapPayload} />
        ) : (
          <div className="text-gray-400">
            No map data yet. Run a scenario that calls tools like traffic, alternates, or places.
          </div>
        )}
      </div>

      {/* classification */}
      {classification && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm uppercase tracking-wider text-gray-400">Classification</div>
            <Pill tone={classification.kind === "unknown" ? "warn" : "ok"}>{classification.kind}</Pill>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <K>Severity</K>
              <div className="font-medium">{classification.severity}</div>
            </div>
            <div>
              <K>Uncertainty</K>
              <div className="font-medium">{classification.uncertainty}</div>
            </div>
          </div>
        </div>
      )}

      {/* chain of thought */}
      {steps.length > 0 && (
        <section className="card p-5">
          <div className="text-sm uppercase tracking-wider text-gray-400 mb-3">Chain of Thought</div>
          <div className="relative">
            {steps.map((s, i) => (
              <StepItem key={s.index ?? i} step={s} index={i} active={i === activeIndex} complete={i <= activeIndex} />
            ))}
          </div>
        </section>
      )}

      {/* clarify panel */}
      {clarify && (
        <div className="card p-5 border-amber-800 bg-amber-950/30">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm uppercase tracking-wider text-amber-300">Clarification needed</div>
            <Pill tone="warn">awaiting</Pill>
          </div>
          <div className="text-gray-200 mb-3">{clarify.question || "Please provide more info."}</div>

          {clarify.expected === "image[]" ? (
            <ImageAnswer
              onSubmit={async (fileList) => {
                const fd = new FormData()
                fd.append("order_id", "order_demo")
                fd.append("session_id", sessionId)
                fd.append("question_id", clarify.question_id)
                Array.from(fileList).forEach((f) => fd.append("images", f))
                const up = await fetch(`${API_BASE}/api/evidence/upload`, { method: "POST", body: fd })
                const { files = [] } = await up.json()

                setClarify(null)
                setStatus("streaming")
                closeStream()
                const url =
                  `${API_BASE}/api/agent/clarify/continue?` +
                  new URLSearchParams({
                    session_id: sessionId,
                    question_id: clarify.question_id,
                    expected: "image[]",
                    answer: JSON.stringify(files),
                  })
                wireSSE(url)
              }}
            />
          ) : Array.isArray(clarify.options) && clarify.options.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {clarify.options.map((opt) => (
                <button key={opt} className="btn btn-primary" onClick={() => resumeWithAnswer(opt)}>
                  {String(opt)}
                </button>
              ))}
            </div>
          ) : clarify.expected === "boolean" ? (
            <div className="flex gap-2">
              <button className="btn btn-primary" onClick={() => resumeWithAnswer("yes")}>
                Yes
              </button>
              <button className="btn btn-ghost" onClick={() => resumeWithAnswer("no")}>
                No
              </button>
            </div>
          ) : (
            <div className="flex gap-2">
              <input
                className="input flex-1"
                placeholder="Type your answer…"
                value={answerDraft}
                onChange={(e) => setAnswerDraft(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && resumeWithAnswer(answerDraft)}
              />
              <button className="btn btn-primary" onClick={() => resumeWithAnswer(answerDraft)}>
                Send
              </button>
            </div>
          )}

          {clarify.options?.length > 0 && (
            <div className="mt-3 text-sm text-gray-400">Options: {clarify.options.join(" / ")}</div>
          )}
          {sessionId && (
            <div className="mt-2 text-xs text-gray-500">
              session: <code>{sessionId}</code>
            </div>
          )}
        </div>
      )}

      {/* summary */}
      {summaryEvt && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm uppercase tracking-wider text-gray-400">Summary</div>
            <Pill
              tone={summaryEvt.outcome === "resolved" ? "ok" : summaryEvt.outcome === "escalated" ? "warn" : "neutral"}
            >
              {summaryEvt.outcome || "—"}
            </Pill>
          </div>

          <div className="rounded-xl bg-[rgba(0,0,0,0.35)] border border-[var(--grab-edge)] p-3">
            <div className="text-gray-200">{summaryText || "—"}</div>
          </div>

          {sessionId && summaryEvt.outcome === "await_input" && (
            <div className="mt-2 text-xs text-gray-500">
              Awaiting response. Session <code>{sessionId}</code> will resume when you answer above.
            </div>
          )}
        </div>
      )}
    </div>
  )

  /* ───────────── CLI view (raw SSE) ───────────── */
  const CLIView = (
    <div className="card p-4">
      <div className="text-xs text-gray-400 mb-2">Raw SSE</div>
      <pre className="cli">{rawLines.map((l, i) => `[${(i + 1).toString().padStart(3, "0")}] ${l}`).join("\n")}</pre>
    </div>
  )

  /* ───────────── top controls + view switcher ───────────── */
  return (
    <div className="space-y-4">
      <div className="flex gap-3 items-center flex-wrap">
        <button className="btn btn-primary" onClick={start} disabled={!scenarioText || status === "streaming"}>
          {status === "streaming" ? "Streaming…" : "Run Scenario"}
        </button>
        <button className="btn btn-ghost" onClick={stop} disabled={status !== "streaming"}>
          Stop
        </button>
        <div className="text-sm text-gray-400 self-center hidden md:block">
          API: <code className="font-mono">{previewUrl || "—"}</code>
        </div>
        <div className="flex-1" />
        <ViewToggle mode={mode} setMode={setMode} />
      </div>

      {error && <div className="card border-rose-800 bg-rose-950/40 p-3">{error}</div>}
      {mode === "gui" ? GUIView : CLIView}
    </div>
  )
}
