// src/components/AgentStream.jsx
"use client"

import React, { useEffect, useRef, useState } from "react"
import { API_BASE, buildRunUrl } from "../utils/api"

// Firebase Messaging (frontend)
import { getMessaging, onMessage, isSupported } from "firebase/messaging"
import { app } from "../lib/firebase" // initialized Firebase app
import { ensureFreshFcmToken, refreshFcmToken } from "../lib/fcm-token"

/* ------------ Small UI helpers ------------ */
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

/* Pretty printer */
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

/* Step card */
function StepItem({ step, index, active = false, complete = false }) {
  const [open, setOpen] = React.useState(true)
  const ok = step.passed === true
  return (
    <div
      id={`step-${index}`}
      className="relative pl-6"
      style={{ animation: `fadeInUp 400ms ease ${index * 80}ms both` }}
      aria-current={active ? "step" : undefined}
    >
      {/* Timeline dot and line */}
      <div className="absolute left-0 top-2">
        <div
          className={`w-3 h-3 rounded-full ${ok ? "bg-emerald-400" : "bg-rose-400"} ring-4 ring-[var(--grab-bg)] ${
            active ? "timeline-dot-active" : ""
          }`}
        />
      </div>
      {index !== 0 && (
        <div
          className={`absolute left-1 top-[-24px] bottom-6 w-[2px] ${complete ? "conn-complete" : "conn-upcoming"}`}
        />
      )}

      <div className={`card p-4 ${active ? "step-active" : ""}`}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Pill>Step {typeof step.index === "number" ? step.index + 1 : "—"}</Pill>
            <div className="font-semibold text-white">{step.intent || "—"}</div>
          </div>
          <div className="flex items-center gap-2">
            <Pill tone={ok ? "ok" : "err"}>{ok ? "passed" : "failed"}</Pill>
            <button type="button" className="btn btn-ghost" onClick={() => setOpen((v) => !v)}>
              {open ? "Hide" : "Show"}
            </button>
          </div>
        </div>

        {/* meta row */}
        <div className="grid md:grid-cols-3 gap-4">
          <div>
            <div className="text-xs text-gray-400 mb-1">Tool</div>
            <div className="font-medium text-[var(--grab-green)]">{step.tool || "none"}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400 mb-1">Assertion</div>
            <div className="font-medium text-gray-200 break-words">{step.assertion || "—"}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400 mb-1">Timestamp</div>
            <div className="font-medium text-gray-200">{step.ts || "—"}</div>
          </div>
        </div>

        {open && (
          <div className="mt-4 grid md:grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-gray-400 mb-1">Params</div>
              <PrettyObject data={step.params} />
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">Observation</div>
              <PrettyObject data={step.observation} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/* GUI/CLI toggle */
function ViewToggle({ mode, setMode }) {
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
        <button onClick={() => setMode("gui")} className={`py-1.5 ${isGUI ? "text-white" : "text-gray-400"}`}>
          GUI Chain
        </button>
        <button onClick={() => setMode("cli")} className={`py-1.5 ${!isGUI ? "text-white" : "text-gray-400"}`}>
          CLI Chain
        </button>
      </div>
    </div>
  )
}

/* keyframes */
const style = document.createElement("style")
style.innerHTML = `
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(12px) }
  to   { opacity: 1; transform: translateY(0) }
}`
if (!document.getElementById("fadeInUpKeyframes")) {
  style.id = "fadeInUpKeyframes"
  document.head.appendChild(style)
}

/* ------------ Main component ------------ */
export default function AgentStream({ scenarioText }) {
  const [events, setEvents] = useState([])
  const [rawLines, setRawLines] = useState([])
  const [status, setStatus] = useState("idle")
  const [error, setError] = useState("")
  const [mode, setMode] = useState("gui")
  const [activeIndex, setActiveIndex] = useState(-1)
  const [isPlaying, setIsPlaying] = useState(false)
  const [followLive, setFollowLive] = useState(true)
  const playSpeed = 900
  const esRef = useRef(null)

  // FCM state
  const [fcmSupported, setFcmSupported] = useState(false)
  const [fcmToken, setFcmToken] = useState("")
  const [notifPermission, setNotifPermission] = useState(Notification?.permission ?? "default")

  const previewUrl = scenarioText
    ? `${API_BASE}/api/agent/run?${new URLSearchParams({ scenario: scenarioText }).toString()}`
    : ""

  // Bootstrap FCM: detect support, hook foreground messages
// In AgentStream.jsx, where you already bootstrap FCM:
useEffect(() => {
  let off = () => {};
  (async () => {
    const supported = await isSupported();
    setFcmSupported(supported);
    if (!supported) return;

    // Ensure SW is registered (root scope)
    const reg = (await navigator.serviceWorker.getRegistration()) ||
                (await navigator.serviceWorker.register("/firebase-messaging-sw.js"));

    const messaging = getMessaging(app);

    off = onMessage(messaging, async (payload) => {
      console.log("[FCM] foreground payload:", payload);

      // If you prefer a toast, show it here and return.

      // Show a native notification while tab is focused:
      if (Notification.permission === "granted") {
        const title = payload?.notification?.title || "Notification";
        const body  = payload?.notification?.body  || "";
        const data  = payload?.data || {};

        // Use the active service worker to show a system notification
        const swr = (await navigator.serviceWorker.getRegistration()) || reg;
        swr?.showNotification(title, {
          body,
          data,                     // carry any deep-link info
          tag: payload?.messageId,  // avoid stacking dupes
          // icon: "/icon-192x192.png", // optional
          requireInteraction: true  // keeps it visible until user clicks
        });
      }
    });
  })();

  return () => off();
}, []);

  // Always keep a fresh token in state when notifications are allowed
  const refreshTokenIfNeeded = async () => {
    try {
      const tok = await ensureFreshFcmToken()
      if (tok) setFcmToken(tok)
    } catch (e) {
      console.warn("[FCM] ensureFreshFcmToken failed:", e)
    }
  }
  useEffect(() => {
    if (Notification?.permission === "granted") {
      refreshTokenIfNeeded()
    }
  }, [])

  const start = async () => {
    if (!scenarioText) return
    if (esRef.current) { esRef.current.close(); esRef.current = null }

    setActiveIndex(-1); setIsPlaying(false); setFollowLive(true)
    setEvents([]); setRawLines([]); setError(""); setStatus("streaming")

    try {
      // Make sure we use a live token
      const liveToken = fcmToken || (await ensureFreshFcmToken())
      if (liveToken && liveToken !== fcmToken) setFcmToken(liveToken)

      const urlWithToken = await buildRunUrl({
        scenario: scenarioText,
        passenger_token: liveToken || undefined,
        customer_token: liveToken || undefined,
      })

      const es = new EventSource(urlWithToken)
      esRef.current = es

      es.onmessage = async (evt) => {
        const line = evt.data
        setRawLines((prev) => [...prev, line])
        if (!line) return

        if (line === "[DONE]") {
          setStatus("done"); es.close(); esRef.current = null; setFollowLive(false)
          return
        }

        try {
          const payload = JSON.parse(line)
          // If backend says UNREGISTERED, rotate the token so the next run succeeds
          const err = payload?.data?.observation?.error
          const errCode =
            err?.errorCode ||
            (typeof err === "object" && JSON.stringify(err).includes('"UNREGISTERED"') ? "UNREGISTERED" : null)
          if (errCode === "UNREGISTERED") {
            const newTok = await refreshFcmToken()
            if (newTok) setFcmToken(newTok)
          }

          setEvents((prev) => [...prev, payload])
        } catch {
          // ignore non-JSON pings
        }
      }

      es.onerror = () => {
        setStatus("error")
        setError("Stream error. Ensure backend is running, CORS allowed, and token is valid.")
        es.close(); esRef.current = null
      }
    } catch (e) {
      setStatus("error"); setError(e.message || "Failed to start stream")
    }
  }

  const stop = () => {
    if (esRef.current) { esRef.current.close(); esRef.current = null }
    setStatus("done"); setIsPlaying(false); setFollowLive(false)
  }

  const classification = events.find((e) => e.type === "classification")?.data
  const steps = events.filter((e) => e.type === "step").map((e) => ({ ...e.data, ts: e.at }))
  const summary = events.find((e) => e.type === "summary")?.data

  useEffect(() => { if (followLive && steps.length > 0) setActiveIndex(steps.length - 1) }, [steps.length, followLive])
  useEffect(() => {
    if (!isPlaying) return
    const id = setInterval(() => setActiveIndex((i) => Math.min((i ?? -1) + 1, steps.length - 1)), playSpeed)
    return () => clearInterval(id)
  }, [isPlaying, steps.length])
  useEffect(() => {
    if (activeIndex < 0) return
    const el = document.getElementById(`step-${activeIndex}`)
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" })
  }, [activeIndex])

  const GUIView = (
    <div className="space-y-6">
      {/* Push status */}
      <div className="card p-4 flex items-center justify-between gap-4">
        <div className="text-sm">
          <div className="font-medium mb-1">Push Delivery</div>
          <div className="text-gray-400">
            {fcmSupported ? "Web Push is supported" : "Web Push not supported"}
            {" • "}
            Permission: <strong>{notifPermission}</strong>
            {fcmToken && (
              <> {" • "} Token: <code className="text-xs">{fcmToken.slice(0, 12)}…{fcmToken.slice(-8)}</code> </>
            )}
          </div>
        </div>
      </div>

      {classification && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm uppercase tracking-wider text-gray-400">Classification</div>
            <Pill tone={classification.kind === "unknown" ? "warn" : "ok"}>{classification.kind}</Pill>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div><K>Severity</K><div className="font-medium">{classification.severity}</div></div>
            <div><K>Uncertainty</K><div className="font-medium">{classification.uncertainty}</div></div>
          </div>
        </div>
      )}

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

      {summary && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm uppercase tracking-wider text-gray-400">Summary</div>
            <Pill tone={summary.outcome === "resolved" ? "ok" : summary.outcome === "escalated" ? "warn" : "neutral"}>
              {summary.outcome}
            </Pill>
          </div>
          <div className="text-gray-200 mb-3">{summary.summary || "—"}</div>
        </div>
      )}
    </div>
  )

  const CLIView = (
    <div className="card p-4">
      <div className="text-xs text-gray-400 mb-2">Raw SSE</div>
      <pre className="cli">{rawLines.map((l, i) => `[${(i + 1).toString().padStart(3, "0")}] ${l}`).join("\n")}</pre>
    </div>
  )

  return (
    <div className="space-y-4">
      <div className="flex gap-3 items-center flex-wrap">
        <button className="btn btn-primary" onClick={start} disabled={!scenarioText || status === "streaming"}>
          {status === "streaming" ? "Streaming…" : "Run Scenario"}
        </button>
        <button className="btn btn-ghost" onClick={stop} disabled={status !== "streaming"}>Stop</button>
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
