import { useEffect, useMemo, useRef, useState } from "react";
import AgentRunner from "../components/agent/AgentRunner.jsx";
import { ensureFreshFcmToken } from "../lib/fcm-token";
import { API_BASE } from "../config";
import ImageAnswer from "../components/AgentStream/ImageAnswer.jsx";
import MerchantMap from "../components/AgentStream/MerchantMap.jsx";
import AltRoutesMap from "../components/AgentStream/AltRoutesMap.jsx";
import "../styles/grabcar.css";

// Layout/blocks
import Sidebar from "../components/dashboard/Sidebar.jsx";
import TopBar from "../components/ui/TopBar.jsx";
import KpiRow from "../components/ui/KpiRow.jsx";
import ChainTimelineBox from "../components/agent/ChainTimelineBox.jsx";
import AgentQuestions from "../components/agent/AgentQuestions.jsx";
import SummaryCard from "../components/agent/SummaryCard.jsx";
import ChainTimeline from "../components/agent/ChainTimeline.jsx";

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

function pickBounds(src) {
  const b =
    src?.bounds ||
    src?.viewport ||
    src?.bbox ||
    src?.boundingBox ||
    src?.area ||
    null;
  if (!b) return null;
  const south =
    num(b.south) ?? num(b.s) ?? num(b.minLat) ?? num(b.minlat) ?? undefined;
  const west =
    num(b.west) ?? num(b.w) ?? num(b.minLng) ?? num(b.minlng) ?? num(b.minLon);
  const north =
    num(b.north) ?? num(b.n) ?? num(b.maxLat) ?? num(b.maxlat) ?? undefined;
  const east =
    num(b.east) ?? num(b.e) ?? num(b.maxLng) ?? num(b.maxlng) ?? num(b.maxLon);
  if ([south, west, north, east].every((x) => Number.isFinite(x))) {
    return { south, west, north, east };
  }
  return null;
}

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
        summary: firstOf(r, ["summary", "name", "id"]) ?? `Route ${i + 1}`,
        durationMin:
          num(firstOf(r, ["duration_min", "durationMin"])) ??
          num(firstOf(r, ["etaNoTraffic", "etaMin"])),
        trafficMin: num(
          firstOf(r, ["etaMin", "duration_traffic_min", "time_min"])
        ),
        raw: r,
        polyline:
          r?.polyline ||
          r?.encodedPolyline ||
          r?.points ||
          r?.overview_polyline?.points ||
          r?.overview_polyline ||
          rMap?.overview_polyline?.points ||
          rMap?.overview_polyline ||
          null,
        path: r?.path,
      });
    });
  if (directAlts) consume(directAlts);
  else if (mapRoutes) consume(mapRoutes);

  const bounds = pickBounds(map) || pickBounds(obs) || pickBounds(data) || null;

  return { alternates: alts, mapUrl: embedUrl, staticUrl, bounds };
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

/* Right panel map chooser */
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

// Prompt modal
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

/** Clarify Modal */
function ClarifyModal({
  clarify,
  answerDraft,
  setAnswerDraft,
  onClose,
  onAnswer,
  onUploadImages,
}) {
  if (!clarify) return null;

  return (
    <div className="gs-modal clarify-modal" role="dialog" aria-modal="true">
      <div className="gs-modal-card">
        <div className="gs-modal-header">
          <div className="gs-title">Clarification needed</div>
          <button className="gs-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="gs-modal-body">
          <div className="mb-3">
            {clarify.question || "Please provide more information."}
          </div>

          {clarify.expected === "image[]" ? (
            <ImageAnswer onSubmit={onUploadImages} />
          ) : Array.isArray(clarify.options) && clarify.options.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {clarify.options.map((opt) => (
                <button
                  key={String(opt)}
                  className="gt-choice-btn"
                  onClick={() => onAnswer(String(opt))}
                >
                  {String(opt)}
                </button>
              ))}
            </div>
          ) : clarify.expected === "boolean" ? (
            <div className="flex gap-2">
              <button className="gt-choice-btn" onClick={() => onAnswer("yes")}>
                Yes
              </button>
              <button className="gt-choice-btn" onClick={() => onAnswer("no")}>
                No
              </button>
            </div>
          ) : (
            <div className="flex gap-2">
              <input
                autoFocus
                className="gt-input flex-1"
                placeholder="Type your answer…"
                value={answerDraft}
                onChange={(e) => setAnswerDraft(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && onAnswer(answerDraft)}
              />
              <button
                className="gt-choice-btn"
                onClick={() => onAnswer(answerDraft)}
              >
                Send
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Routes Modal (map + options) */
function RoutesModal({ open, routes, bounds, onPick, onClose }) {
  const [selIdx, setSelIdx] = useState(0);
  if (!open || !Array.isArray(routes) || routes.length === 0) return null;

  const questionRoutes = routes.map((r, i) => ({
    name: r.name || r.summary || `Route ${i + 1}`,
    etaMin: r.trafficMin ?? r.etaMin ?? r.durationMin ?? null,
    etaNoTraffic: r.durationMin ?? r.etaNoTraffic ?? null,
    distanceKm: r.distanceKm ?? r.distance_km ?? r.distance ?? null,
    mapUrl: r.mapUrl || "",
    staticMapUrl: r.staticMapUrl || "",
    raw: r.raw ?? r,
  }));

  return (
    <div className="gs-modal clarify-modal" role="dialog" aria-modal="true">
      <div className="gs-modal-card" style={{ maxWidth: 980 }}>
        <div className="gs-modal-header">
          <div className="gs-title">Choose a route</div>
          <button className="gs-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="gs-modal-body">
          <AltRoutesMap
            routes={routes.map((r) => ({
              summary: r.summary ?? r.name,
              durationMin: r.durationMin ?? r.etaNoTraffic ?? r.etaMin,
              trafficMin: r.trafficMin ?? r.etaMin,
              polyline: r.polyline,
              path: r.path,
              overview_polyline: r.overview_polyline,
            }))}
            bounds={bounds || undefined}
            selectedRoute={selIdx}
            onChangeSelected={(i) => setSelIdx(i)}
            onConfirm={(i) => onPick(i, questionRoutes[i])}
          />

          <div className="mt-4">
            <AgentQuestions
              routes={questionRoutes}
              onPick={(i, r) => {
                setSelIdx(i);
                onPick(i, r);
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function GrabCar() {
  const [prompt, setPrompt] = useState("");
  const [scenarioText, setScenarioText] = useState("");
  const hasRun = useMemo(() => !!scenarioText, [scenarioText]);

  // CMD overlay
  const [overlayOpen, setOverlayOpen] = useState(() => {
    return localStorage.getItem("gt.cmdOverlayDismissed") !== "1";
  });
  const overlayAutoOpenedRef = useRef(false);

  // NEW: routes modal toggle
  const [routesModalOpen, setRoutesModalOpen] = useState(false);

  const [showModal, setShowModal] = useState(false);
  const [showTicker, setShowTicker] = useState(true);

  const [summary, setSummary] = useState("");
  const [alerts, setAlerts] = useState(0);
  const [eta, setEta] = useState(null);
  const [distanceKm, setDistanceKm] = useState(null);

  const [events, setEvents] = useState([]);
  const [alternates, setAlternates] = useState([]);
  const [routeBounds, setRouteBounds] = useState(null);
  const [mapEmbed, setMapEmbed] = useState({ mapUrl: "", staticUrl: "" });

  // clarify/resume state
  const [sessionId, setSessionId] = useState("");
  const [clarify, setClarify] = useState(null);
  const [answerDraft, setAnswerDraft] = useState("");
  const resumeEsRef = useRef(null);

  // merchant pins
  const [merchantPins, setMerchantPins] = useState([]);
  const [merchantCenter, setMerchantCenter] = useState(null);

  // FCM tokens
  const [driverToken, setDriverToken] = useState("");
  const [passengerToken, setPassengerToken] = useState("");
  const [customerToken, setCustomerToken] = useState("");

  const altsShownRef = useRef(false);
  const lastSummaryRef = useRef("");
  const notifiedRef = useRef(new Set()); // <<== notification deduper

  // helper: notify once per logical key
  function notifyOnce(key, title, body) {
    if (!key) return;
    if (notifiedRef.current.has(key)) return;
    notifiedRef.current.add(key);
    notify(title, body);
  }

  // Close overlay with ESC
  useEffect(() => {
    if (!overlayOpen) return;
    const onKey = (e) => {
      if (e.key === "Escape") {
        setOverlayOpen(false);
        try {
          localStorage.setItem("gt.cmdOverlayDismissed", "1");
        } catch {}
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [overlayOpen]);

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

  // When a run starts, force-show overlay, and reset deduper
  useEffect(() => {
    if (hasRun) {
      try {
        localStorage.removeItem("gt.cmdOverlayDismissed");
      } catch {}
      setOverlayOpen(true);
      overlayAutoOpenedRef.current = true;
      notifiedRef.current.clear(); // reset per session
    }
  }, [hasRun]);

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

    // Merchant alternates (GrabFood)
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
    const {
      alternates: alts,
      mapUrl,
      staticUrl,
      bounds,
    } = extractRoutingBits(ev);
    if (alts.length) {
      setAlternates(alts);
      if (bounds) setRouteBounds(bounds);

      // Auto-open Routes modal when alternates appear
      setRoutesModalOpen(true);

      if (!altsShownRef.current) {
        altsShownRef.current = true;
        const best = alts[0];
        const msg = best
          ? `Alternates ready. Best: ${best.name} • ${
              best.etaMin ?? "—"
            } min • ${best.distanceKm ?? "—"} km`
          : "Alternate routes are available.";
        notifyOnce(`alts:${sessionId}`, "GrabCar: Alternates found", msg);
      }
    }
    if (mapUrl || staticUrl) {
      setMapEmbed({ mapUrl: mapUrl || "", staticUrl: staticUrl || "" });
      setMerchantPins([]);
      setMerchantCenter(null);
    }

    // Collect summary text (guard with lastSummaryRef)
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
          // (Optional) If you want to notify summary, keep it single-shot per distinct text:
          // notifyOnce(`summary:${sessionId}:${str.length}`, "GrabCar: Update", str);
        }
      }
    }

    // IMPORTANT: removed generic per-message notifier (this caused spam)
    // if (typeof ev.message === "string" && ev.message.trim()) {
    //   notify("GrabCar", ev.message.trim());
    // }
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

    notifyOnce(
      `route:${sessionId}:${index}:${route?.name || index}`,
      "GrabCar: Route selected",
      `${route?.name || `Route ${index + 1}`}: ${etaText} • ${distText}`
    );

    // close the routes modal after selection
    setRoutesModalOpen(false);
    setAlternates([]); // hide questions after pick
  };

  const hasQuestion = Boolean(clarify) || (alternates && alternates.length > 0);

  return (
    <div className="grabtaxi-page">
      {/* ===== CMD overlay ===== */}
      {overlayOpen && (
        <div className="cmd-overlay" role="dialog" aria-modal="true">
          <div className="cmd-window">
            <div className="cmd-header">
              <div className="cmd-title">
                <span className="blink-dot" aria-hidden="true"></span>
                <span>Live Agent Session</span>
                <span className="cmd-session-id">
                  {sessionId ? `#${String(sessionId).slice(-6)}` : "—"}
                </span>
              </div>
              <button
                className="cmd-close"
                aria-label="Close"
                title="Close (Esc)"
                onClick={() => {
                  setOverlayOpen(false);
                  try {
                    localStorage.setItem("gt.cmdOverlayDismissed", "1");
                  } catch {}
                }}
              >
                ×
              </button>
            </div>
            <div className="cmd-body">
              <ChainTimeline events={events} />
            </div>
          </div>
        </div>
      )}

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

          <ChainTimelineBox
            className="mt-3"
            title="Agent Timeline"
            events={events}
            fullHeight={!hasQuestion}
            onMaximize={() => setOverlayOpen(true)}
          />

          {/* Hide questions list on page when routes modal is open */}
          {!routesModalOpen && !overlayOpen && (
            <AgentQuestions routes={alternates} onPick={onPickRoute} />
          )}

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
                // We no longer notify here to avoid double toasts;
                // handleEvent() manages summary changes with lastSummaryRef.
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

      {/* Prompt modal */}
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

          // FORCE open CMD overlay for a new session
          try {
            localStorage.removeItem("gt.cmdOverlayDismissed");
          } catch {}
          setOverlayOpen(true);

          // reset guards
          setRoutesModalOpen(false);
          overlayAutoOpenedRef.current = true;

          // reset notification deduper for the new run
          notifiedRef.current.clear();
        }}
      />

      {/* Clarify modal */}
      <ClarifyModal
        clarify={clarify}
        answerDraft={answerDraft}
        setAnswerDraft={setAnswerDraft}
        onClose={() => setClarify(null)}
        onAnswer={(ans) => resumeWithAnswer(ans)}
        onUploadImages={(files) => uploadImagesAndResume(files)}
      />

      {/* Routes modal (map + options + default route) */}
      <RoutesModal
        open={routesModalOpen && alternates.length > 0}
        routes={alternates}
        bounds={routeBounds}
        onPick={onPickRoute}
        onClose={() => setRoutesModalOpen(false)}
      />
    </div>
  );
}
