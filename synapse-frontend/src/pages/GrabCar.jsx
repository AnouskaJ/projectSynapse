import { useEffect, useMemo, useRef, useState } from "react";
import AgentRunner from "../components/agent/AgentRunner.jsx";
import { ensureFreshFcmToken } from "../lib/fcm-token";
import "../styles/grabcar.css";
import Sidebar from "../components/dashboard/Sidebar.jsx";

/** HARD-CODED TOKENS (hidden from UI) */
const HARDCODED_DRIVER_TOKEN = "fcm_dvr_6hJ9Q2vT8mN4aXs7bK1pR5eW3zL0cY8u";
const HARDCODED_PASSENGER_TOKEN = "fcm_psg_9Xk2Qw7Lm4Na8Rt3Vp5Ye1Ui6Oz0Bc2D";
const HARDCODED_CUSTOMER_TOKEN = "fcm_cst_7mQ4Vr2Tp9Aa3Xs6Kn1Le5Wy0Zb8Cd3F"; // optional

// ---------- localStorage ----------
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

// ---------- atoms ----------
function Kpi({ label, value, subtle }) {
  return (
    <div className="kpi-pill">
      <div className="label">{label}</div>
      <div className={`value ${subtle ? "opacity-70" : ""}`}>{value}</div>
    </div>
  );
}
const Skel = ({ className = "" }) => (
  <div
    className={`h-3 w-full animate-pulse rounded bg-white/10 ${className}`}
  />
);

// ---------- helpers ----------
const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
};
function safeStringify(obj) {
  const seen = new WeakSet();
  try {
    return JSON.stringify(
      obj,
      (k, v) => {
        if (typeof v === "object" && v !== null) {
          if (seen.has(v)) return "[circular]";
          seen.add(v);
        }
        return v;
      },
      2
    );
  } catch {
    try {
      return String(obj);
    } catch {
      return "";
    }
  }
}
function coerceSummary(x) {
  if (x == null) return "";
  if (typeof x === "string") return x;
  if (Array.isArray(x))
    return x
      .map((i) => (typeof i === "string" ? i : safeStringify(i)))
      .join("\n");
  if (typeof x === "object") {
    if (typeof x.text === "string") return x.text;
    if (typeof x.message === "string") return x.message;
    return safeStringify(x);
  }
  return String(x);
}
function firstOf(obj, keys, xform = (x) => x) {
  for (const k of keys) {
    const v = obj?.[k];
    if (v !== undefined && v !== null) return xform(v);
  }
  return undefined;
}
/** Pull alternates + map from any event shape */
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

  const consume = (arr) => {
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
  };

  if (directAlts) consume(directAlts);
  else if (mapRoutes) consume(mapRoutes);

  return { alternates: alts, mapUrl: embedUrl, staticUrl };
}

// ----- notifications (simple) -----
function canNotify() {
  return typeof window !== "undefined" && "Notification" in window;
}
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

// ---------- UI helpers ----------
function CollapsibleValue({ value }) {
  const text =
    typeof value === "string"
      ? value
      : typeof value === "number" || typeof value === "boolean"
      ? String(value)
      : safeStringify(value);

  const isLong = text.length > 220;
  if (!isLong) {
    return (
      <pre className="mt-0.5 whitespace-pre-wrap break-words rounded-lg border border-[var(--grab-edge)] bg-black/20 p-2 text-[12px] leading-relaxed font-mono select-text">
        {text}
      </pre>
    );
  }
  return (
    <details className="mt-1 rounded-lg border border-[var(--grab-edge)] bg-black/20">
      <summary className="cursor-pointer px-2 py-1 text-[12px] text-[var(--grab-muted)]">
        (click to expand)
      </summary>
      <pre className="whitespace-pre-wrap break-words p-2 text-[12px] leading-relaxed font-mono select-text">
        {text}
      </pre>
    </details>
  );
}
function KeyVal({ title, data }) {
  if (!data || typeof data !== "object") return null;
  const entries = Object.entries(data);
  if (!entries.length) return null;
  return (
    <div className="space-y-1">
      {title && (
        <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--grab-muted)]">
          {title}
        </div>
      )}
      <div className="space-y-2">
        {entries.map(([k, v]) => (
          <div key={k} className="min-w-0">
            <div className="text-[11px] uppercase tracking-wide text-[var(--grab-muted)]">
              {k}
            </div>
            <CollapsibleValue value={v} />
          </div>
        ))}
      </div>
    </div>
  );
}
function ChainTimeline({ events }) {
  if (!events.length) {
    return <div className="gt-empty gt-card text-sm">Waiting for events…</div>;
  }
  const pullMessage = (ev) =>
    ev?.message ??
    ev?.data?.message ??
    ev?.observation?.message ??
    ev?.data?.observation?.message;

  return (
    <div className="gt-timeline-scroll">
      {events.map((ev, i) => {
        const t = ev?.type || "event";
        const data = ev?.data || {};
        const pill =
          t === "step"
            ? "Step"
            : t === "classification"
            ? "Classification"
            : t === "summary"
            ? "Summary"
            : t === "session"
            ? "Session"
            : t === "done"
            ? "Done"
            : t === "error"
            ? "Error"
            : "Event";

        if (
          t === "error" &&
          (String(ev.error) === "[object Event]" ||
            String(ev.error) === "{}" ||
            String(ev.error).toLowerCase().includes("abort") ||
            String(ev.error).toLowerCase().includes("close"))
        )
          return null;

        const friendlyMsg = pullMessage(ev);

        return (
          <div key={i} className="gt-timeline-item">
            <div className="flex items-center gap-2">
              <span className="gt-pill">{pill}</span>
              {t === "step" && typeof data?.index === "number" && (
                <span className="text-sm font-medium">#{data.index + 1}</span>
              )}
              <div className="gt-meta ml-auto">
                {ev.at ? new Date(ev.at).toLocaleString() : ""}
              </div>
            </div>

            <div className="mt-1">
              {t === "step" && (
                <div className="text-base font-medium">
                  {data.intent || ev.intent || "step"}
                </div>
              )}
              {t === "classification" && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium">
                    {data.kind || "classification"}
                  </span>
                  {data.severity && (
                    <span className="rounded-full border border-[var(--grab-edge)] px-2 py-0.5 text-[11px]">
                      severity: {data.severity}
                    </span>
                  )}
                  {typeof data.uncertainty === "number" && (
                    <span className="rounded-full border border-[var(--grab-edge)] px-2 py-0.5 text-[11px]">
                      uncertainty: {data.uncertainty}
                    </span>
                  )}
                </div>
              )}
              {t === "summary" && (
                <div className="whitespace-pre-wrap text-sm">
                  {coerceSummary(ev.data ?? ev.summary)}
                </div>
              )}
              {t === "error" && (
                <div className="text-sm text-red-400">
                  {typeof ev.error === "string"
                    ? ev.error
                    : safeStringify(ev.error)}
                </div>
              )}
            </div>

            {typeof friendlyMsg === "string" && friendlyMsg.trim() && (
              <details className="gt-collapse mt-2">
                <summary>Message</summary>
                <div className="mt-2">
                  <CollapsibleValue value={friendlyMsg} />
                </div>
              </details>
            )}

            {t === "step" && (
              <details className="gt-collapse mt-2">
                <summary>Details</summary>
                <div className="mt-2 space-y-3">
                  <KeyVal
                    title="Tool"
                    data={data.tool ? { tool: data.tool } : null}
                  />
                  <KeyVal title="Params" data={ev.params || data.params} />
                  <KeyVal
                    title="Observation"
                    data={ev.observation || data.observation}
                  />
                </div>
              </details>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------- Route choice ----------
function RouteChoice({ routes = [], onPick }) {
  if (!Array.isArray(routes) || !routes.length) return null;
  return (
    <div className="gt-card p-3 mt-3 gt-choice-card">
      <div className="mb-2 text-sm font-semibold">Agent Questions</div>
      <div className="space-y-2">
        {routes.map((r, idx) => {
          const title = r.name || r.id || `Route ${idx + 1}`;
          const details = [
            r.etaMin != null ? `${r.etaMin} min` : null,
            r.etaNoTraffic != null
              ? `${r.etaNoTraffic} min (no traffic)`
              : null,
            r.distanceKm != null ? `${r.distanceKm} km` : null,
          ]
            .filter(Boolean)
            .join(" · ");

          return (
            <button
              key={idx}
              className="gt-choice-btn"
              onClick={() => onPick?.(idx, r)}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium">{title}</div>
                <div className="text-xs text-[var(--grab-muted)]">
                  {details || "—"}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ---------- Map panel ----------
function MapPanel({ mapUrl, staticUrl }) {
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
          className="h-[420px] w-full"
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

// ---------- Prompt modal ----------
function PromptModal({ open, initial, onClose, onSave }) {
  const [text, setText] = useState(initial || "");
  const [showTicker, setShowTicker] = useState(true);
  useEffect(() => setText(initial || ""), [initial, open]);
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-black/70 p-4">
      <div className="mt-16 w-full max-w-3xl rounded-2xl border border-[var(--grab-edge)] bg-[var(--grab-bg)] p-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-lg font-semibold">View &amp; Edit Prompt</h3>
          <button className="btn btn-ghost text-sm" onClick={onClose}>
            Close
          </button>
        </div>
        <textarea
          rows={8}
          className="w-full rounded-xl border border-[var(--grab-edge)] bg-transparent p-3 outline-none focus:border-[var(--grab-accent)]"
          placeholder="Describe the scenario…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onClose}>
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

// ---------- Page ----------
export default function GrabCar() {
  const [prompt, setPrompt] = useState("");
  const [scenarioText, setScenarioText] = useState("");
  const hasRun = useMemo(() => !!scenarioText, [scenarioText]);

  const [showModal, setShowModal] = useState(false);
  const [summary, setSummary] = useState("");
  const [alerts, setAlerts] = useState(0);
  const [eta, setEta] = useState(null);
  const [distanceKm, setDistanceKm] = useState(null);

  const [events, setEvents] = useState([]);
  const [alternates, setAlternates] = useState([]);
  const [mapEmbed, setMapEmbed] = useState({ mapUrl: "", staticUrl: "" });

  // Hidden tokens (still passed to backend)
  const [driverToken] = useState(HARDCODED_DRIVER_TOKEN);
  const [passengerToken] = useState(HARDCODED_PASSENGER_TOKEN);
  const [customerToken] = useState(HARDCODED_CUSTOMER_TOKEN);

  // spam guards
  const altsShownRef = useRef(false);
  const lastSummaryRef = useRef("");

  useEffect(() => {
    (async () => {
      try {
        await ensureFreshFcmToken();
      } catch {}
      await ensurePermission();
    })();
  }, []);

  useEffect(() => {
    const stored = readPrompt();
    setPrompt(stored);
    if (stored) setScenarioText(stored);
  }, []);

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
    };

    setEvents((prev) => [...prev, ev]);

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
    if (mapUrl || staticUrl)
      setMapEmbed({ mapUrl: mapUrl || "", staticUrl: staticUrl || "" });

    if (ev.type === "summary") {
      const text = coerceSummary(ev.data ?? ev.summary);
      setSummary(text);
      if (text && text !== lastSummaryRef.current) {
        lastSummaryRef.current = text;
        notify("GrabCar: Update", text);
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

  const [showTicker, setShowTicker] = useState(true);

  return (
    <div className="grabtaxi-page">
      {/* ====== TOPBAR ====== */}
      <header className="gt-topbar">
        <div className="gt-topbar-title">GrabCar</div>
        <div className="gt-topbar-tools">
          <div className="gt-search">
            <svg width="16" height="16" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="m21 21l-4.3-4.3m1.3-4.7A7 7 0 1 1 4 12a7 7 0 0 1 14 0"
              />
            </svg>
            <input placeholder="Search rides, drivers..." />
          </div>
          <button
            className="btn btn-primary"
            onClick={() => setShowModal(true)}
          >
            View &amp; Edit Prompt
          </button>
          <button className="gt-icon">
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M12 22a2 2 0 0 0 2-2H10a2 2 0 0 0 2 2m6-6v-5a6 6 0 1 0-12 0v5l-2 2v1h16v-1z"
              />
            </svg>
          </button>
        </div>
      </header>

      {/* ====== BODY GRID ====== */}
      <div className="gt-grid">
        {/* LEFT: SIDEBAR */}
        <aside className="gt-sidebar">
          <Sidebar />
        </aside>

        {/* MIDDLE: TIMELINE + CHOICES */}
        <main className="gt-middle">
          {showTicker && (
            <div className="gt-ticker" role="status" aria-live="polite">
              <span className="live">Live</span>
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
          )}

          <div className="gt-card mt-3 gt-timeline-card">
            <div className="flex items-center justify-between p-3">
              <div className="text-sm font-semibold">Agent Timeline</div>
              <div className="gt-dim text-xs">{events.length} items</div>
            </div>
            <ChainTimeline events={events} />
          </div>

          <RouteChoice routes={alternates} onPick={onPickRoute} />

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
                const text = coerceSummary(s);
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

        {/* RIGHT: KPIs + MAP + DRIVER + SUMMARY */}
        <section className="gt-right">
          <div className="kpi-row">
            <Kpi label="Sessions" value="128" />
            <Kpi
              label="Avg. ETA"
              value={eta != null ? `${eta} min` : "—"}
              subtle={eta == null}
            />
            <Kpi
              label="Distance"
              value={distanceKm != null ? `${distanceKm} km` : "—"}
              subtle={distanceKm == null}
            />
            <div className="kpi-pill">
              <div className="label">Alerts</div>
              <div className="badge">{alerts ?? 0}</div>
            </div>
          </div>

          <div className="mt-3">
            <MapPanel mapUrl={mapEmbed.mapUrl} staticUrl={mapEmbed.staticUrl} />
          </div>

          <div className="gt-driver mt-3">
            <div className="left">
              <img
                src="https://randomuser.me/api/portraits/men/46.jpg"
                alt="driver"
              />
              <div>
                <div className="font-semibold">Ramesh Kumar</div>
                <div className="gt-dim text-xs">Maruti Suzuki • TN 57 AD 3604</div>
              </div>
            </div>
            <div className="chip">En route</div>
          </div>

          <div className="gt-card summary-card p-3 mt-3">
            <div className="mb-2 text-sm font-semibold">Summary</div>
            {!summary ? (
              <div className="space-y-2">
                <Skel />
                <Skel />
                <Skel className="w-2/3" />
              </div>
            ) : (
              <pre className="summary-pre">{summary}</pre>
            )}
          </div>
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
          altsShownRef.current = false;
          lastSummaryRef.current = "";
        }}
      />
    </div>
  );
}
