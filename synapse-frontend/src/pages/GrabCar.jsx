import { useEffect, useMemo, useRef, useState } from "react";
import AgentRunner from "../components/agent/AgentRunner.jsx";
import { ensureFreshFcmToken } from "../lib/fcm-token";
import { API_BASE } from "../config";
import ImageAnswer from "../components/AgentStream/ImageAnswer.jsx";
import MerchantMap from "../components/AgentStream/MerchantMap.jsx";
import "../styles/grabcar.css";

// Layout/blocks
import Sidebar from "../components/dashboard/Sidebar.jsx";
import TopBar from "../components/ui/TopBar.jsx";
import KpiRow from "../components/ui/KpiRow.jsx";
import ChainTimelineBox from "../components/agent/ChainTimelineBox.jsx";
import AgentQuestions from "../components/agent/AgentQuestions.jsx";
import SummaryCard from "../components/agent/SummaryCard.jsx";

/** (Kept for fallback only; real tokens are fetched dynamically) */
const HARDCODED_DRIVER_TOKEN = "fcm_dvr_6hJ9Q2vT8mN4aXs7bK1pR5eW3zL0cY8u";
const HARDCODED_PASSENGER_TOKEN = "fcm_psg_9Xk2Qw7Lm4Na8Rt3Vp5Ye1Ui6Oz0Bc2D";
const HARDCODED_CUSTOMER_TOKEN = "fcm_cst_7mQ4Vr2Tp9Aa8Xs6Kn1Le5Wy0Zb8Cd3F";

// ----- Prompt presets for quick demos -----
const SCENARIO_PRESETS = {
  grabfood: {
    title: "GrabFood",
    scenario:
      "Order GF-10234 from 'Nasi Goreng House, Velachery' to DLF IT Park, Manapakkam. Kitchen is quoting a 45 minute prep time and the driver is waiting. Proactively inform the customer, minimize driver idle time, and suggest faster nearby alternatives.",
  },
  grabmart: {
    title: "GrabMart – Damage Dispute",
    scenario:
      "Order GM-20987 from 'QuickMart, T. Nagar' to Olympia Tech Park, Guindy. At the doorstep, the customer reports a spilled drink. It's unclear if this is merchant or driver fault. Mediate the dispute fairly on-site.",
  },
  grabexpress: {
    title: "GrabExpress",
    scenario:
      "A valuable parcel is being delivered to Adyar. The driver has arrived but the recipient is not responding. Initiate contact, and if they can't receive it, suggest a safe drop-off or a nearby secure locker.",
  },
  grabcar: {
    title: "GrabCar",
    scenario:
      "An urgent airport ride from SRMIST Chennai to Chennai International Airport (MAA) for flight 6E 5119. A major accident is blocking the main route. Find the fastest alternative and inform both passenger and driver.",
  },
};
// ------------------------------------------

const GRABCAR_KEY = "synapse.prompt_grabcar";
const GENERIC_KEY = "synapse.prompt";
const readPrompt = () => {
  try {
    const a = localStorage.getItem(GRABCAR_KEY);
    if (a && a.trim()) return a.trim();
    const b = localStorage.getItem(GENERIC_KEY);
    if (b && b.trim()) return b.trim();
  } catch {}
  return "";
};
const writePrompt = (t) => {
  try {
    localStorage.setItem(GRABCAR_KEY, t);
    localStorage.setItem(GENERIC_KEY, t);
  } catch {}
};

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
};
const firstOf = (obj, keys, xform = (x) => x) => {
  for (const k of keys) {
    const v = obj?.[k];
    if (v !== undefined && v !== null) return xform(v);
  }
  return undefined;
};
function extractRoutingBits(ev) {
  const data = ev?.data || ev || {};
  const obs = data?.observation || ev?.observation || {};
  const map = obs?.map || data?.map || {};
  const embedUrl =
    firstOf(ev, ["mapUrl", "embedUrl", "embed_url"]) ??
    firstOf(data, ["mapUrl", "embedUrl", "embed_url"]) ??
    firstOf(map, ["embedUrl", "embed_url"]) ??
    "";
  const staticUrl =
    firstOf(ev, ["staticMapUrl", "static_url", "staticUrl"]) ??
    firstOf(data, ["staticMapUrl", "static_url", "staticUrl"]) ??
    firstOf(map, ["staticMapUrl", "static_url", "staticUrl"]) ??
    "";

  let alts = [];
  const directAlts = Array.isArray(data?.alternates) ? data.alternates : null;
  const mapRoutes = Array.isArray(map?.routes) ? map.routes : null;
  const consume = (arr) =>
    arr.forEach((r, i) => {
      const rMap = r?.map || {};
      alts.push({
        name: firstOf(r, ["name", "id", "summary"]) ?? `Route ${i + 1}`,
        etaMin: num(
          firstOf(r, [
            "etaMin",
            "eta_minutes",
            "eta",
            "duration_traffic_min",
            "durationMin",
            "duration_min",
            "time_min",
          ])
        ),
        etaNoTraffic: num(
          firstOf(r, ["etaNoTraffic", "duration_min", "durationNoTrafficMin"])
        ),
        distanceKm: num(firstOf(r, ["distanceKm", "distance_km", "distance"])),
        mapUrl:
          firstOf(r, ["mapUrl", "embedUrl", "embed_url"]) ??
          firstOf(rMap, ["embedUrl", "embed_url"]) ??
          "",
        staticMapUrl:
          firstOf(r, ["staticMapUrl", "static_url", "staticUrl"]) ??
          firstOf(rMap, ["staticMapUrl", "static_url", "StaticUrl"]) ??
          "",
        raw: r,
      });
    });
  if (directAlts) consume(directAlts);
  else if (mapRoutes) consume(mapRoutes);
  return { alternates: alts, mapUrl: embedUrl, staticUrl };
}

// notifications
const canNotify = () =>
  typeof window !== "undefined" && "Notification" in window;
async function ensurePermission() {
  if (!canNotify()) return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  try {
    return (await Notification.requestPermission()) === "granted";
  } catch {
    return false;
  }
}
async function notify(title, body) {
  if (!(await ensurePermission())) return;
  try {
    new Notification(title, { body });
  } catch {}
}

/* Right panel map chooser:
   - If staticUrl/embedUrl exists → iframe/static image (routes).
   - Else if we have merchant pins → render MerchantMap. */
function MapPanel({ mapUrl, staticUrl, merchants, center }) {
  if (!mapUrl && !staticUrl && merchants?.length) {
    const c = center || {
      lat: merchants[0]?.lat,
      lng: merchants[0]?.lng ?? merchants[0]?.lon,
    };
    return (
      <div className="map-frame">
        <MerchantMap center={c} merchants={merchants} />
      </div>
    );
  }
  if (staticUrl) {
    return (
      <div className="map-frame">
        <img src={staticUrl} alt="route" className="h-auto w-full" />
      </div>
    );
  }
  if (mapUrl) {
    return (
      <div className="map-frame">
        <iframe
          key={mapUrl}
          title="map"
          src={mapUrl}
          allowFullScreen
          loading="lazy"
        />
      </div>
    );
  }
  return (
    <div className="gt-card p-4 text-sm text-[var(--grab-muted)]">
      Map will render once available.
    </div>
  );
}

// Prompt modal (polished, uses gs-* styles from grabcar.css)
function PromptModal({ open, initial, onClose, onSave }) {
  const [text, setText] = useState(initial || "");
  const [presetKey, setPresetKey] = useState("");

  useEffect(() => {
    setText(initial || "");
    setPresetKey("");
  }, [initial, open]);

  if (!open) return null;

  const handleChoosePreset = (key) => {
    setPresetKey(key);
    const chosen = SCENARIO_PRESETS[key];
    if (chosen?.scenario) setText(chosen.scenario);
  };

  return (
    <div className="gs-modal">
      <div className="gs-modal-card">
        <div className="gs-modal-header">
          <div className="gs-title">View &amp; Edit Prompt</div>

          <div className="gs-header-actions">
            <span className="gs-label">Preset</span>

            {/* custom select with visible chevron */}
            <div className="relative">
              <select
                className="gs-select"
                value={presetKey}
                onChange={(e) => handleChoosePreset(e.target.value)}
              >
                <option value="">— Choose —</option>
                <option value="grabfood">GrabFood</option>
                <option value="grabmart">GrabMart – Damage Dispute</option>
                <option value="grabexpress">GrabExpress</option>
                <option value="grabcar">GrabCar</option>
              </select>
              <span
                aria-hidden
                style={{
                  position: "absolute",
                  right: 8,
                  top: "50%",
                  transform: "translateY(-50%)",
                  pointerEvents: "none",
                  fontSize: 12,
                  color: "var(--grab-muted)",
                }}
              >
                ▼
              </span>
            </div>

            <button
              className="btn sm"
              title="Clear"
              onClick={() => {
                setPresetKey("");
                setText("");
              }}
            >
              Reset
            </button>

            <button className="btn sm" onClick={onClose}>
              Close
            </button>
          </div>
        </div>

        {presetKey && (
          <div className="gs-preset-hint">
            Loaded:{" "}
            <span className="gs-preset-name">
              {SCENARIO_PRESETS[presetKey]?.title}
            </span>
          </div>
        )}

        <textarea
          className="gs-textarea"
          placeholder="Describe the scenario…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={9}
        />

        <div className="gs-modal-footer">
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={() => {
              const v = (text || "").trim();
              if (!v) return;
              writePrompt(v);
              onSave?.(v);
              onClose();
            }}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

export default function GrabCar() {
  const [prompt, setPrompt] = useState("");
  const [scenarioText, setScenarioText] = useState("");
  const hasRun = useMemo(() => !!scenarioText, [scenarioText]);

  const [showModal, setShowModal] = useState(false);
  const [showTicker, setShowTicker] = useState(true);

  const [summary, setSummary] = useState("");
  const [alerts, setAlerts] = useState(0);
  const [eta, setEta] = useState(null);
  const [distanceKm, setDistanceKm] = useState(null);

  const [events, setEvents] = useState([]);
  const [alternates, setAlternates] = useState([]);
  const [mapEmbed, setMapEmbed] = useState({ mapUrl: "", staticUrl: "" });

  // clarify/resume state
  const [sessionId, setSessionId] = useState("");
  const [clarify, setClarify] = useState(null);
  const [answerDraft, setAnswerDraft] = useState("");
  const resumeEsRef = useRef(null);

  // merchant pins (for GrabFood alternates)
  const [merchantPins, setMerchantPins] = useState([]);
  const [merchantCenter, setMerchantCenter] = useState(null);

  // FCM tokens — dynamic (fixes INVALID_ARGUMENT)
  const [driverToken, setDriverToken] = useState("");
  const [passengerToken, setPassengerToken] = useState("");
  const [customerToken, setCustomerToken] = useState("");

  const altsShownRef = useRef(false);
  const lastSummaryRef = useRef("");

  useEffect(() => {
    (async () => {
      try {
        const tok = await ensureFreshFcmToken();
        if (tok && typeof tok === "string") {
          setCustomerToken(tok);
          setDriverToken(tok);
          setPassengerToken(tok);
        } else {
          setCustomerToken(HARDCODED_CUSTOMER_TOKEN);
          setDriverToken(HARDCODED_DRIVER_TOKEN);
          setPassengerToken(HARDCODED_PASSENGER_TOKEN);
        }
      } catch {
        setCustomerToken(HARDCODED_CUSTOMER_TOKEN);
        setDriverToken(HARDCODED_DRIVER_TOKEN);
        setPassengerToken(HARDCODED_PASSENGER_TOKEN);
      }
      await ensurePermission();
    })();
  }, []);

  // cleanup resume SSE on unmount
  useEffect(() => {
    return () => {
      try {
        resumeEsRef.current?.close?.();
      } catch {}
      resumeEsRef.current = null;
    };
  }, []);

  useEffect(() => {
    const stored = readPrompt();
    setPrompt(stored);
    if (stored) setScenarioText(stored);
  }, []);

  // ---- resume SSE helper + resume functions ----
  function wireResumeSSE(url) {
    try {
      resumeEsRef.current?.close?.();
    } catch {}
    const es = new EventSource(url, { withCredentials: false });
    resumeEsRef.current = es;
    es.onmessage = (e) => {
      const raw = (e?.data ?? "").trim();
      if (!raw) return;
      if (raw === "[DONE]") {
        try {
          es.close();
        } catch {}
        resumeEsRef.current = null;
        return;
      }
      try {
        const obj = JSON.parse(raw);
        handleEvent(obj);
      } catch {}
    };
    es.onerror = () => {
      try {
        es.close();
      } catch {}
      resumeEsRef.current = null;
    };
  }

  async function resumeWithAnswer(answer) {
    if (!sessionId || !clarify) return;
    const qs = new URLSearchParams({
      session_id: sessionId,
      question_id: clarify.question_id || "",
      expected: clarify.expected || "string",
    });
    if (clarify.expected === "boolean") {
      qs.set(
        "answer",
        String(answer).toLowerCase().startsWith("y") ? "yes" : "no"
      );
    } else {
      qs.set(
        "answer",
        typeof answer === "string" ? answer : JSON.stringify(answer)
      );
    }
    setClarify(null);
    setAnswerDraft("");
    wireResumeSSE(`${API_BASE}/api/agent/clarify/continue?${qs}`);
  }

  async function uploadImagesAndResume(fileList) {
    if (!sessionId || !clarify) return;
    const fd = new FormData();
    fd.append("order_id", "order_demo");
    fd.append("session_id", sessionId);
    fd.append("question_id", clarify.question_id || "evidence_images");
    Array.from(fileList).forEach((f) => fd.append("images", f));
    const up = await fetch(`${API_BASE}/api/evidence/upload`, {
      method: "POST",
      body: fd,
    });
    const { files = [] } = await up.json();
    setClarify(null);
    setAnswerDraft("");
    const qs = new URLSearchParams({
      session_id: sessionId,
      question_id: clarify.question_id || "evidence_images",
      expected: "image[]",
      answer: JSON.stringify(files),
    });
    wireResumeSSE(`${API_BASE}/api/agent/clarify/continue?${qs}`);
  }
  // ------------------------------------------------

  const handleEvent = (incoming) => {
    if (!incoming || typeof incoming !== "object") return;

    const ev = {
      ...incoming,
      params:
        incoming.params ??
        incoming.data?.params ??
        incoming?.observation?.params,
      observation: incoming.observation ?? incoming.data?.observation,
      message:
        incoming.message ??
        incoming.data?.message ??
        incoming.observation?.message ??
        incoming.data?.observation?.message,
      tool: incoming.tool ?? incoming.data?.tool ?? incoming.observation?.tool,
    };

    setEvents((prev) => [...prev, ev]);

    // capture session + clarify
    if (ev.type === "session" && ev?.data?.session_id) {
      setSessionId(ev.data.session_id);
    }
    if (ev.type === "clarify" && ev?.data) {
      if (ev.data.session_id) setSessionId(ev.data.session_id);
      setClarify(ev.data);
    }

    // Merchant alternates (GrabFood): draw client-side map with pins
    const merchants =
      ev?.observation?.merchants ||
      ev?.data?.observation?.merchants ||
      ev?.data?.merchants;
    if (Array.isArray(merchants) && merchants.length > 0) {
      setMerchantPins(merchants);
      const latParam =
        num(firstOf(ev.params, ["lat", "latitude"])) ?? merchants[0]?.lat;
      const lonParam =
        num(firstOf(ev.params, ["lon", "lng", "longitude"])) ??
        merchants[0]?.lng ??
        merchants[0]?.lon;
      setMerchantCenter({ lat: latParam, lng: lonParam });
    }

    // Route map state (GrabCar)
    const { alternates: alts, mapUrl, staticUrl } = extractRoutingBits(ev);
    if (alts.length) {
      setAlternates(alts);
      if (!altsShownRef.current) {
        altsShownRef.current = true;
        const best = alts[0];
        const msg = best
          ? `Alternates ready. Best: ${best.name} • ${
              best.etaMin ?? "—"
            } min • ${best.distanceKm ?? "—"} km`
          : "Alternate routes are available.";
        notify("GrabCar: Alternates found", msg);
      }
    }
    if (mapUrl || staticUrl) {
      setMapEmbed({ mapUrl: mapUrl || "", staticUrl: staticUrl || "" });
      // Prefer route embed over merchant pins
      setMerchantPins([]);
      setMerchantCenter(null);
    }

    // Collect summary text across agent variants
    if (
      ev.type === "summary" ||
      ev.type === "final" ||
      ev.type === "done" ||
      ev.type === "result"
    ) {
      const textCandidate =
        ev?.data?.summary ??
        ev?.summary ??
        ev?.observation?.summary ??
        ev?.data?.final ??
        ev?.data?.result ??
        ev?.message ??
        ev?.data?.message ??
        ev?.observation?.message;

      const str =
        typeof textCandidate === "string"
          ? textCandidate
          : Array.isArray(textCandidate)
          ? textCandidate.join("\n")
          : (textCandidate && (textCandidate.text || textCandidate.message)) ||
            "";

      if (str) {
        setSummary(str);
        if (str !== lastSummaryRef.current) {
          lastSummaryRef.current = str;
          notify("GrabCar: Update", str);
        }
      }
    }

    if (typeof ev.message === "string" && ev.message.trim()) {
      notify("GrabCar", ev.message.trim());
    }
  };

  const onPickRoute = (index, route) => {
    setEvents((prev) => [
      ...prev,
      {
        type: "step",
        at: new Date().toISOString(),
        data: {
          intent: "route_selected",
          params: { index, title: route?.name || `Route ${index + 1}` },
        },
      },
    ]);

    if (route?.mapUrl || route?.staticMapUrl) {
      setMapEmbed({
        mapUrl: route.mapUrl || "",
        staticUrl: route.staticMapUrl || "",
      });
      setMerchantPins([]);
      setMerchantCenter(null);
    }

    const etaText =
      route?.etaMin != null
        ? `${route.etaMin} min`
        : route?.etaNoTraffic != null
        ? `${route.etaNoTraffic} min (no traffic)`
        : "—";
    const distText = route?.distanceKm != null ? `${route.distanceKm} km` : "—";
    notify(
      "GrabCar: Route selected",
      `${route?.name || `Route ${index + 1}`}: ${etaText} • ${distText}`
    );
    setAlternates([]);
  };

  // --- compute whether a question panel is visible
  const hasQuestion = Boolean(clarify) || (alternates && alternates.length > 0);

  return (
    <div className="grabtaxi-page">
      {/* TOPBAR */}
      <TopBar title="ProjectSynapse" onOpenPrompt={() => setShowModal(true)} />

      {/* GRID */}
      <div className="gt-grid">
        {/* LEFT */}
        <aside className="gt-sidebar">
          <Sidebar />
        </aside>

        {/* MIDDLE */}
        <main className="gt-middle">
          {showTicker && (
            <div className="gt-ticker-overlay" role="status" aria-live="polite">
              <div className="ticker-content">
                <span className="live blink">Live</span>
                <span className="gt-dim">Real-time feed connected</span>
                <span className="gt-dim">
                  Driver locations updating every 10s
                </span>
                <button
                  className="gt-ticker-close"
                  aria-label="Hide live feed"
                  title="Hide"
                  onClick={() => setShowTicker(false)}
                >
                  ×
                </button>
              </div>
              <div className="ticker-dots">
                <span />
                <span />
                <span />
              </div>
            </div>
          )}

          {/* Timeline (auto-grow to full height when there’s no question panel) */}
          <ChainTimelineBox
            className="mt-3"
            title="Agent Timeline"
            events={events}
            fullHeight={!hasQuestion}
          />

          {/* Clarify UI */}
          {clarify && (
            <div className="gt-card p-3 mt-3">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-semibold">Clarification needed</div>
                <div className="gt-dim text-xs">awaiting</div>
              </div>
              <div className="mb-3">
                {clarify.question || "Please provide more information."}
              </div>

              {clarify.expected === "image[]" ? (
                <ImageAnswer onSubmit={uploadImagesAndResume} />
              ) : Array.isArray(clarify.options) && clarify.options.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {clarify.options.map((opt) => (
                    <button
                      key={opt}
                      className="gt-choice-btn"
                      onClick={() => resumeWithAnswer(String(opt))}
                    >
                      {String(opt)}
                    </button>
                  ))}
                </div>
              ) : clarify.expected === "boolean" ? (
                <div className="flex gap-2">
                  <button
                    className="gt-choice-btn"
                    onClick={() => resumeWithAnswer("yes")}
                  >
                    Yes
                  </button>
                  <button
                    className="gt-choice-btn"
                    onClick={() => resumeWithAnswer("no")}
                  >
                    No
                  </button>
                </div>
              ) : (
                <div className="flex gap-2">
                  <input
                    className="gt-input flex-1"
                    placeholder="Type your answer…"
                    value={answerDraft}
                    onChange={(e) => setAnswerDraft(e.target.value)}
                    onKeyDown={(e) =>
                      e.key === "Enter" && resumeWithAnswer(answerDraft)
                    }
                  />
                  <button
                    className="gt-choice-btn"
                    onClick={() => resumeWithAnswer(answerDraft)}
                  >
                    Send
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Route suggestions */}
          <AgentQuestions routes={alternates} onPick={onPickRoute} />

          {/* SSE runner */}
          {hasRun && (
            <AgentRunner
              scenarioText={scenarioText}
              driverToken={driverToken}
              passengerToken={passengerToken}
              customerToken={customerToken}
              onKpi={(k) => {
                if (typeof k?.etaMin === "number") setEta(k.etaMin);
                if (typeof k?.distanceKm === "number")
                  setDistanceKm(k.distanceKm);
                if (typeof k?.alerts === "number") setAlerts(k.alerts);
              }}
              onSummary={(s) => {
                const text =
                  typeof s === "string"
                    ? s
                    : Array.isArray(s)
                    ? s.join("\n")
                    : (s && (s.text || s.message)) || "";
                setSummary(text);
                if (text && text !== lastSummaryRef.current) {
                  lastSummaryRef.current = text;
                  notify("GrabCar: Update", text);
                }
              }}
              onEvent={handleEvent}
            />
          )}
        </main>

        {/* RIGHT */}
        <section className="gt-right">
          <KpiRow
            items={[
              { label: "Sessions", value: "128" },
              {
                label: "Avg. ETA",
                value: eta != null ? `${eta} min` : "—",
                subtle: eta == null,
              },
              {
                label: "Distance",
                value: distanceKm != null ? `${distanceKm} km` : "—",
                subtle: distanceKm == null,
              },
              { label: "Alerts", value: alerts ?? 0, badge: true },
            ]}
          />

          <div className="mt-3">
            <MapPanel
              mapUrl={mapEmbed.mapUrl}
              staticUrl={mapEmbed.staticUrl}
              merchants={merchantPins}
              center={merchantCenter}
            />
          </div>

          <SummaryCard summary={summary} className="mt-3" />
        </section>
      </div>

      <PromptModal
        open={showModal}
        initial={prompt}
        onClose={() => setShowModal(false)}
        onSave={(v) => {
          setPrompt(v);
          setScenarioText(v);
          setSummary("");
          setEvents([]);
          setAlternates([]);
          setMapEmbed({ mapUrl: "", staticUrl: "" });
          setEta(null);
          setDistanceKm(null);
          setAlerts(0);
          setClarify(null);
          setAnswerDraft("");
          setSessionId("");
          setMerchantPins([]);
          setMerchantCenter(null);
          try {
            resumeEsRef.current?.close?.();
          } catch {}
          resumeEsRef.current = null;
          altsShownRef.current = false;
          lastSummaryRef.current = "";
        }}
      />
    </div>
  );
}
