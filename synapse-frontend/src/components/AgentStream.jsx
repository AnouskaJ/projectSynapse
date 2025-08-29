import React, { useMemo, useRef, useState } from "react";
import { buildRunUrl } from "../utils/api";

/**
 * Streams events from /api/agent/run and renders:
 * - classification
 * - each step (intent, tool, params, assertion, observation, success)
 * - final summary
 */
export default function AgentStream({ runParams }) {
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState("idle"); // idle | streaming | done | error
  const [error, setError] = useState("");
  const esRef = useRef(null);

  const url = useMemo(() => (runParams ? buildRunUrl(runParams) : ""), [runParams]);

  const start = () => {
    if (!url) return;
    // Close any previous stream
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    setEvents([]);
    setError("");
    setStatus("streaming");

    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (evt) => {
      try {
        if (!evt.data) return;
        if (evt.data === "[DONE]") {
          setStatus("done");
          es.close();
          esRef.current = null;
          return;
        }
        const parsed = JSON.parse(evt.data);
        setEvents((prev) => [...prev, parsed]);
      } catch (e) {
        // Could be a non-JSON ping; ignore
      }
    };

    es.onerror = (e) => {
      setStatus("error");
      setError("Stream error. Check backend is running and CORS/URL is correct.");
      es.close();
      esRef.current = null;
    };
  };

  const stop = () => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setStatus("done");
  };

  // Partition events
  const classification = events.find((e) => e.type === "classification");
  const steps = events.filter((e) => e.type === "step").map((e) => e.data);
  const summary = events.find((e) => e.type === "summary");

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <button className="btn btn-primary" onClick={start} disabled={!url || status === "streaming"}>
          {status === "streaming" ? "Streaming…" : "Run Scenario"}
        </button>
        <button className="btn btn-ghost" onClick={stop} disabled={status !== "streaming"}>
          Stop
        </button>
        <div className="text-sm text-gray-400 self-center select-all">
          API: <code className="kbd">{url}</code>
        </div>
      </div>

      {error && <div className="card border-rose-800 bg-rose-950/40">{error}</div>}

      {classification && (
        <section className="card">
          <h3 className="font-semibold text-lg mb-3" style={{ color: "#00B14F" }}>Classification</h3>
          <pre className="text-sm whitespace-pre-wrap">
{JSON.stringify(classification.data, null, 2)}
          </pre>
        </section>
      )}

      {steps.length > 0 && (
        <section className="card">
          <h3 className="font-semibold text-lg mb-3" style={{ color: "#00B14F" }}>Chain of Thought (Action Steps)</h3>
          <ol className="space-y-3 list-decimal list-inside">
            {steps.map((s, i) => (
              <li key={i} className="p-3 rounded-xl bg-black/20 border border-grab-edge">
                <div className="text-sm text-gray-300 mb-2">#{s.idx} • {s.ts}</div>
                <div className="grid md:grid-cols-2 gap-3">
                  <div>
                    <div className="text-sm"><span className="text-gray-400">intent:</span> <span className="font-medium">{s.intent}</span></div>
                    <div className="text-sm"><span className="text-gray-400">tool:</span> <span className="font-medium">{s.tool}</span></div>
                    {s.assertion && <div className="text-sm"><span className="text-gray-400">assertion:</span> <code className="kbd">{s.assertion}</code></div>}
                    <div className="text-sm"><span className="text-gray-400">success:</span> <span className={s.success ? "text-emerald-400" : "text-rose-400"}>{String(s.success)}</span></div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-400">params</div>
                    <pre className="text-xs whitespace-pre-wrap">
{JSON.stringify(s.params, null, 2)}
                    </pre>
                    <div className="text-sm text-gray-400 mt-2">observation</div>
                    <pre className="text-xs whitespace-pre-wrap">
{JSON.stringify(s.observation, null, 2)}
                    </pre>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {summary && (
        <section className="card">
          <h3 className="font-semibold text-lg mb-3" style={{ color: "#00B14F" }}>Summary</h3>
          <pre className="text-sm whitespace-pre-wrap">
{JSON.stringify(summary.data, null, 2)}
          </pre>
        </section>
      )}
    </div>
  );
}
