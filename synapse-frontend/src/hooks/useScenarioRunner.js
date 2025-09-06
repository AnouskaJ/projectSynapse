import { useEffect, useMemo, useRef, useState } from "react";
import { subscribeSSE } from "../services/api";

// A very small state machine for the streamed run.
// Expected event shapes (examples):
// { type:"kpi", data:{ etaMin: 31, distanceKm: 21.1 } }
// { type:"map", data:{ embedUrl, routes:[...] } }
// { type:"step", data:{ idx, title, tool, assertion, status:"passed|failed|await_input", params, observation } }
// { type:"clarify", data:{ question_id, question, expected, options? } }
// { type:"summary", data:{ status:"resolved|... ", text:"..." } }

export function useScenarioRunner({ service, runUrlBuilder, autostartPrompt }) {
  const [running, setRunning] = useState(false);
  const [kpi, setKpi] = useState({ live: true, etaMin: null, delayMin: null, distanceKm: null, alerts: 0 });
  const [map, setMap] = useState(null);
  const [routes, setRoutes] = useState([]);            // alternate routes
  const [steps, setSteps] = useState([]);              // step stream
  const [clarify, setClarify] = useState(null);        // pending ask_user
  const [summary, setSummary] = useState(null);
  const closerRef = useRef(null);

  const start = (scenarioText) => {
    if (!scenarioText || running) return;
    setRunning(true);
    setSteps([]); setClarify(null); setSummary(null); setRoutes([]);

    const url = runUrlBuilder(scenarioText);
    closerRef.current = subscribeSSE(url, {
      onOpen: () => {},
      onError: () => setRunning(false),
      onMessage: (msg) => {
        switch (msg.type) {
          case "kpi":
            setKpi((k)=>({ ...k, ...msg.data }));
            break;
          case "map":
            setMap(msg.data || null);
            break;
          case "routes":
            setRoutes(msg.data || []);
            break;
          case "step":
            setSteps((arr)=> [...arr, msg.data]);
            if (msg.data.status === "await_input" && msg.data.clarify) {
              setClarify(msg.data.clarify);
            }
            break;
          case "clarify":
            setClarify(msg.data);
            break;
          case "summary":
            setSummary(msg.data);
            break;
          default:
            break;
        }
      }
    });
  };

  const stop = () => {
    if (closerRef.current) closerRef.current();
    setRunning(false);
  };

  // autorun when a prompt is present
  useEffect(() => {
    if (autostartPrompt && autostartPrompt.trim()) start(autostartPrompt.trim());
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autostartPrompt]);

  return { running, start, stop, kpi, map, routes, steps, clarify, setClarify, summary };
}
