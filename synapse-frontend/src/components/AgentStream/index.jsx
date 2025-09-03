// src/components/AgentStream/index.jsx

"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { getMessaging, onMessage, isSupported } from "firebase/messaging";
import { app } from "../../lib/firebase";
import { ensureFreshFcmToken, refreshFcmToken } from "../../lib/fcm-token";
import { API_BASE } from "../../config";
import { buildRunUrl } from "../../utils/api";

/* Local components */
import Pill from "./Pill";
import PrettyObject, { K } from "./PrettyObject";
import MapBox from "./MapBox";
import StepItem from "./StepItem";
import ViewToggle from "./ViewToggle";
import ImageAnswer from "./ImageAnswer";
import AltRoutesMap from "./AltRoutesMap";

/* Fade-in animation keyframes (one-time inject) */
if (!document.getElementById("fadeInUpKeyframes")) {
  const st = document.createElement("style");
  st.id = "fadeInUpKeyframes";
  st.textContent = "@keyframes fadeInUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}";
  document.head.appendChild(st);
}

export default function AgentStream({ scenarioText }) {
  /* ───────────────────── state ───────────────────── */
  const [events, setEvents] = useState([]);
  const [rawLines, setRawLines] = useState([]);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [mode, setMode] = useState("gui");
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [followLive, setFollowLive] = useState(true);
  const esRef = useRef(null);

  // clarify
  const [sessionId, setSessionId] = useState("");
  const [clarify, setClarify] = useState(null);
  const [answerDraft, setAnswerDraft] = useState("");

  // FCM
  const [fcmSupported, setFcmSupported] = useState(false);
  const [fcmToken, setFcmToken] = useState("");
  const [notifPermission, setNotifPermission] = useState(Notification?.permission ?? "default");

  const previewUrl = scenarioText
    ? `${API_BASE}/api/agent/run?${new URLSearchParams({ scenario: scenarioText }).toString()}`
    : "";

  /* ── push bootstrap ── */
  useEffect(() => {
    let off = () => {};
    (async () => {
      const supported = await isSupported();
      setFcmSupported(supported);
      if (!supported) return;

      const reg =
        (await navigator.serviceWorker.getRegistration()) ||
        (await navigator.serviceWorker.register("/firebase-messaging-sw.js"));

      const messaging = getMessaging(app);
      off = onMessage(messaging, async (payload) => {
        if (Notification.permission === "granted") {
          const title = payload?.notification?.title || "Notification";
          const body = payload?.notification?.body || "";
          const data = payload?.data || {};
          const swr = (await navigator.serviceWorker.getRegistration()) || reg;
          swr?.showNotification(title, { body, data, tag: payload?.messageId, requireInteraction: true });
        }
      });
    })();
    return () => off();
  }, []);

  useEffect(() => {
    if (Notification?.permission === "granted") ensureFreshFcmToken().then((t) => t && setFcmToken(t));
  }, []);

  /* ── SSE helpers ── */
  const closeStream = () => {
    try {
      esRef.current?.close?.();
    } catch {}
    esRef.current = null;
  };

  const handleSSELine = async (line) => {
    setRawLines((p) => [...p, line]);
    if (!line) return;
    if (line === "[DONE]") {
      setStatus("done");
      closeStream();
      setFollowLive(false);
      return;
    }

    try {
      const payload = JSON.parse(line);

      // session id
      if (payload?.type === "session" && payload?.data?.session_id) setSessionId(payload.data.session_id);
      if (payload?.type === "clarify" && payload?.data?.session_id) setSessionId(payload.data.session_id);

      // auto-rotate FCM token on UNREGISTERED
      const err = payload?.data?.observation?.error;
      const errCode =
        err?.errorCode ||
        (typeof err === "object" && JSON.stringify(err).includes('"UNREGISTERED"') ? "UNREGISTERED" : null);
      if (errCode === "UNREGISTERED") {
        const t = await refreshFcmToken();
        if (t) setFcmToken(t);
      }

      // clarify panel
      if (payload?.type === "clarify") {
        setClarify(payload.data || null);
        setStatus("awaiting");
      }

      setEvents((p) => [...p, payload]);
    } catch {
      /* ignore ping */
    }
  };

  const wireSSE = (url) => {
    const es = new EventSource(url);
    esRef.current = es;
    es.onmessage = (e) => handleSSELine(e.data);
    es.onerror = () => {
      setStatus("error");
      setError("Stream error. Check backend, CORS, token.");
      closeStream();
    };
  };

  /* ── start / stop ── */
  const start = async () => {
    if (!scenarioText) return;
    closeStream();
    setActiveIndex(-1);
    setIsPlaying(false);
    setFollowLive(true);
    setEvents([]);
    setRawLines([]);
    setError("");
    setClarify(null);
    setSessionId("");
    setStatus("streaming");

    try {
      if (Notification && Notification.permission !== "granted") {
        const perm = await Notification.requestPermission();
        setNotifPermission(perm);
        if (perm !== "granted") {
          setStatus("error");
          setError("Enable notifications to receive FCM pushes.");
          return;
        }
      }

      const liveTok = (await ensureFreshFcmToken()) || fcmToken;
      if (!liveTok) {
        setStatus("error");
        setError("Could not obtain FCM token.");
        return;
      }
      if (liveTok !== fcmToken) setFcmToken(liveTok);

      const url = await buildRunUrl({
        scenario: scenarioText,
        passenger_token: liveTok,
        customer_token: liveTok,
        driver_token: liveTok,
      });
      wireSSE(url);
    } catch (e) {
      setStatus("error");
      setError(e.message || "Failed to start stream");
    }
  };

  const stop = () => {
    closeStream();
    setStatus("done");
    setIsPlaying(false);
    setFollowLive(false);
  };

  const resumeWithAnswer = async (answer) => {
    if (!sessionId) return setError("Missing session id");
    closeStream();
    setStatus("streaming");
    try {
      const liveTok = fcmToken || (await ensureFreshFcmToken());
      if (liveTok && liveTok !== fcmToken) setFcmToken(liveTok);

      const qs = new URLSearchParams();
      qs.set("session_id", sessionId);
      qs.set("question_id", clarify?.question_id);
      qs.set("answer", answer); // Correctly set the single answer parameter

      if (liveTok) {
        qs.set("passenger_token", liveTok);
        qs.set("customer_token", liveTok);
        qs.set("driver_token", liveTok);
      }
      
      wireSSE(`${API_BASE}/api/agent/clarify/continue?${qs}`);
      setClarify(null);
      setAnswerDraft("");
    } catch (e) {
      setStatus("error");
      setError(e.message || "Failed to resume");
    }
  };

  /* ── derive data ── */
  const classification = useMemo(() => events.find((e) => e.type === "classification")?.data, [events]);
  const steps = useMemo(() => events.filter((e) => e.type === "step").map((e) => ({ ...e.data, ts: e.at })), [events]);
  const summaryEvt = useMemo(() => events.find((e) => e.type === "summary")?.data, [events]);

  // live map payload (most recent)
  const mapPayload = useMemo(() => {
    if (!steps.length) return null;
    let idx = activeIndex >= 0 ? activeIndex : steps.length - 1;
    for (let i = idx; i >= 0; i--) {
      const m = steps[i]?.observation?.map;
      if (m) return m;
    }
    return null;
  }, [steps, activeIndex]);

  const summaryText = useMemo(() => {
    if (!summaryEvt) return "";
    const msg = summaryEvt.message || summaryEvt.summary;
    if (msg && String(msg).trim()) return msg;
    const kind = classification?.kind;
    const sev = classification?.severity;
    const stepsCount = summaryEvt?.metrics?.steps;
    const outcome = summaryEvt?.outcome;
    const lastMsg = steps.length ? steps.at(-1)?.final_message || steps.at(-1)?.finalMessage : "";
    const bits = [];
    if (outcome) bits.push(`Outcome: ${outcome}`);
    if (typeof stepsCount === "number") bits.push(`${stepsCount} step${stepsCount === 1 ? "" : "s"}`);
    if (kind) bits.push(`Kind: ${kind}${sev ? ` (${sev})` : ""}`);
    if (lastMsg) bits.push(lastMsg);
    return bits.join(" • ");
  }, [summaryEvt, classification, steps]);

  /* follow-live / play-through */
  useEffect(() => {
    if (followLive && steps.length) setActiveIndex(steps.length - 1);
  }, [steps.length, followLive]);
  useEffect(() => {
    if (!isPlaying) return;
    const id = setInterval(() => setActiveIndex((i) => Math.min((i ?? -1) + 1, steps.length - 1)), 900);
    return () => clearInterval(id);
  }, [isPlaying, steps.length]);
  useEffect(() => {
    if (activeIndex < 0) return;
    const el = document.getElementById(`step-${activeIndex}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [activeIndex]);

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
          <Pill tone={mapPayload ? "ok" : "warn"}>
            {mapPayload ? "live" : "no data"}
          </Pill>
        </div>
        {mapPayload ? (
          mapPayload.kind === "directions" &&
          (mapPayload.routes?.length ?? 0) > 0 ? (
            <AltRoutesMap
              routes={mapPayload.routes}
              bounds={mapPayload.bounds}
            />
          ) : (
            <MapBox payload={mapPayload} />
          )
        ) : (
          <div className="text-gray-400">
            No map data yet. Run a scenario that calls tools like traffic,
            alternates, or places.
          </div>
        )}
      </div>

      {/* classification */}
      {classification && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm uppercase tracking-wider text-gray-400">
              Classification
            </div>
            <Pill tone={classification.kind === "unknown" ? "warn" : "ok"}>
              {classification.kind}
            </Pill>
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
      {(steps?.length ?? 0) > 0 && (
        <section className="card p-5">
          <div className="text-sm uppercase tracking-wider text-gray-400 mb-3">
            Chain of Thought
          </div>
          <div className="relative">
            {(steps || []).map((s, i) => (
              <StepItem
                key={s.index ?? i}
                step={s}
                index={i}
                active={i === activeIndex}
                complete={i <= activeIndex}
              />
            ))}
          </div>
        </section>
      )}

      {/* clarify panel */}
      {clarify && (
        <div className="card p-5 border-amber-800 bg-amber-950/30">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm uppercase tracking-wider text-amber-300">
              Clarification needed
            </div>
            <Pill tone="warn">awaiting</Pill>
          </div>
          <div className="text-gray-200 mb-3">
            {clarify.question || "Please provide more info."}
          </div>

          {clarify.expected === "image[]" ? (
            <ImageAnswer
              onSubmit={async (fileList) => {
                const fd = new FormData();
                fd.append("order_id", "order_demo");
                fd.append("session_id", sessionId);
                fd.append("question_id", clarify.question_id);
                Array.from(fileList).forEach((f) => fd.append("images", f));
                const up = await fetch(`${API_BASE}/api/evidence/upload`, {
                  method: "POST",
                  body: fd,
                });
                const { files = [] } = await up.json();

                setClarify(null);
                setStatus("streaming");
                closeStream();
                const url =
                  `${API_BASE}/api/agent/clarify/continue?` +
                  new URLSearchParams({
                    session_id: sessionId,
                    question_id: clarify.question_id,
                    expected: "image[]",
                    answer: JSON.stringify(files),
                  });
                wireSSE(url);
              }}
            />
          ) : Array.isArray(clarify.options) && clarify.options.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {clarify.options.map((opt) => (
                <button
                  key={opt}
                  className="btn btn-primary"
                  onClick={() => resumeWithAnswer(opt)}
                >
                  {String(opt)}
                </button>
              ))}
            </div>
          ) : clarify.expected === "boolean" ? (
            <div className="flex gap-2">
              <button
                className="btn btn-primary"
                onClick={() => resumeWithAnswer("yes")}
              >
                Yes
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => resumeWithAnswer("no")}
              >
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
                onKeyDown={(e) =>
                  e.key === "Enter" && resumeWithAnswer(answerDraft)
                }
              />
              <button
                className="btn btn-primary"
                onClick={() => resumeWithAnswer(answerDraft)}
              >
                Send
              </button>
            </div>
          )}

          {clarify.options?.length > 0 && (
            <div className="mt-3 text-sm text-gray-400">
              Options: {clarify.options.join(" / ")}
            </div>
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
            <div className="text-sm uppercase tracking-wider text-gray-400">
              Summary
            </div>
            <Pill
              tone={
                summaryEvt.outcome === "resolved"
                  ? "ok"
                  : summaryEvt.outcome === "escalated"
                  ? "warn"
                  : "neutral"
              }
            >
              {summaryEvt.outcome || "—"}
            </Pill>
          </div>

          <div className="rounded-xl bg-[rgba(0,0,0,0.35)] border border-[var(--grab-edge)] p-3">
            <div className="text-gray-200">{summaryText || "—"}</div>
          </div>

          {sessionId && summaryEvt.outcome === "await_input" && (
            <div className="mt-2 text-xs text-gray-500">
              Awaiting response. Session <code>{sessionId}</code> will resume
              when you answer above.
            </div>
          )}
        </div>
      )}
    </div>
  );

  /* ───────────── CLI view ───────────── */
  const CLIView = (
    <div className="card p-4">
      <div className="text-xs text-gray-400 mb-2">Raw SSE</div>
      <pre className="cli">
        {rawLines
          .map((l, i) => `[${(i + 1).toString().padStart(3, "0")}] ${l}`)
          .join("\n")}
      </pre>
    </div>
  );

  /* ───────────── UI - top controls & switcher ───────────── */
  return (
    <div className="space-y-4">
      <div className="flex gap-3 items-center flex-wrap">
        <button
          className="btn btn-primary"
          onClick={start}
          disabled={!scenarioText || status === "streaming"}
        >
          {status === "streaming" ? "Streaming…" : "Run Scenario"}
        </button>
        <button
          className="btn btn-ghost"
          onClick={stop}
          disabled={status !== "streaming"}
        >
          Stop
        </button>
        <div className="text-sm text-gray-400 self-center hidden md:block">
          API: <code className="font-mono">{previewUrl || "—"}</code>
        </div>
        <div className="flex-1" />
        <ViewToggle mode={mode} setMode={setMode} />
      </div>

      {error && (
        <div className="card border-rose-800 bg-rose-950/40 p-3">{error}</div>
      )}
      {mode === "gui" ? GUIView : CLIView}
    </div>
  );
}