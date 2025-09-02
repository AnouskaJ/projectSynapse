/* src/components/AgentStream/StepItem.jsx */
import React, { useState, useMemo, lazy, Suspense } from "react";
import Pill from "./Pill";
import PrettyObject, { K } from "./PrettyObject";
import StepEmbedMap from "./StepEmbedMap";
import { MAPS_BROWSER_KEY } from "../../config";

/* Lazy-load the heavy map only when needed */
const AltRoutesMap = lazy(() => import("./AltRoutesMap"));
const MerchantMap = lazy(() => import("./MerchantMap"));

/* Helper → build a simple Directions embed URL */
const buildEmbed = (m, p = {}) => {
  const origin =
    p.origin_place || p.origin_any || p.origin ||
    m.origin_place || m.origin_any || "";
  const dest =
    p.dest_place || p.dest_any || p.destination ||
    m.dest_place || m.dest_any || "";
  if (!origin || !dest || !MAPS_BROWSER_KEY) return null;

  const mode = (p.mode || m.mode || "DRIVING").toLowerCase();
  return (
    "https://www.google.com/maps/embed/v1/directions" +
    `?key=${encodeURIComponent(MAPS_BROWSER_KEY)}` +
    `&origin=${encodeURIComponent(origin)}` +
    `&destination=${encodeURIComponent(dest)}` +
    `&mode=${mode}`
  );
};

export default function StepItem({ step, index, active = false, complete = false }) {
  const [open, setOpen] = useState(true);
  const ok = step.passed === true;

  /* Strip noisy keys so PrettyObject stays readable */
  const strip = (obj) => {
    const c = { ...obj };
    ["options", "awaiting", "session_id", "map"].forEach((k) => delete c[k]);
    return c;
  };

  /* -------- decide what to render as `mapElement` -------- */
  const mapElement = useMemo(() => {

    const isAltCalc     = step.tool === "calculate_alternative_route";
    const isCheckTraffic = step.tool === "check_traffic";

    /* ── calculate_alternative_route → show all alternatives ── */
    if (isAltCalc && m.kind === "directions" && m.routes?.length) {
      return (
        <Suspense fallback={<div className="h-96 w-full bg-black/20" />}>
          {/* showAlternatives defaults to true ⇒ full list & coloured lines */}
          <AltRoutesMap routes={m.routes} />
        </Suspense>
      );
    }

    /* ── check_traffic → simple Google embed (single blue line) ── */
    if (isCheckTraffic) {
      const url = m.embedUrl || buildEmbed(m, step.params);
      return url ? <StepEmbedMap url={url} /> : null;
    }
    if (step.tool === "get_nearby_merchants" && step.observation?.merchants?.length) {
      const merchants = step.observation.merchants;
      const center = { lat: merchants[0].lat, lng: merchants[0].lng ?? merchants[0].lon };
      return (
        <Suspense fallback={<div className="h-96 w-full bg-black/20" />}>
          <MerchantMap center={center} merchants={merchants} />
        </Suspense>
      );
    }

    const m = step?.observation?.map;
    if (!m) return null;
   
    /* ── all other tools ── */
    if (m.embedUrl) return <StepEmbedMap url={m.embedUrl} />;
 
    const url = buildEmbed(m, step.params);
    return url ? <StepEmbedMap url={url} /> : null;
  }, [step]);

  /* ------------------- JSX layout ------------------- */
  return (
    <div
      id={`step-${index}`}
      className="relative pl-6"
      style={{ animation: `fadeInUp 400ms ease ${index * 80}ms both` }}
    >
      {/* timeline dot */}
      <div className="absolute left-0 top-2">
        <div
          className={`w-3 h-3 rounded-full ${
            ok ? "bg-emerald-400" : "bg-rose-400"
          } ring-4 ring-[var(--grab-bg)]
             ${active ? "timeline-dot-active" : ""}`}
        />
      </div>
      {index !== 0 && (
        <div
          className={`absolute left-1 top-[-24px] bottom-6 w-[2px] ${
            complete ? "conn-complete" : "conn-upcoming"
          }`}
        />
      )}

      <div className={`card p-4 ${active ? "step-active" : ""}`}>
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Pill>Step {typeof step.index === "number" ? step.index + 1 : "—"}</Pill>
            <div className="font-semibold text-white">{step.intent || "—"}</div>
          </div>
          <div className="flex items-center gap-2">
            <Pill tone={ok ? "ok" : "err"}>{ok ? "passed" : "failed"}</Pill>
            <button className="btn btn-ghost" onClick={() => setOpen(!open)}>
              {open ? "Hide" : "Show"}
            </button>
          </div>
        </div>

        {/* Meta */}
        <div className="grid md:grid-cols-3 gap-4">
          <div><K>Tool</K><div className="font-medium text-[var(--grab-green)]">{step.tool}</div></div>
          <div><K>Assertion</K><div className="font-medium break-words">{step.assertion || "—"}</div></div>
          <div><K>Timestamp</K><div className="font-medium">{step.ts || "—"}</div></div>
        </div>

        {/* Params + Observation */}
        {open && (
          <div className="mt-4 grid md:grid-cols-2 gap-4">
            <div><K>Params</K><PrettyObject data={strip(step.params)} /></div>
            <div><K>Observation</K><PrettyObject data={strip(step.observation)} /></div>
          </div>
        )}

        {/* Map */}
        {mapElement && <div className="mt-4">{mapElement}</div>}
      </div>
    </div>
  );
}
