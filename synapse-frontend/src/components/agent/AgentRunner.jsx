import { useEffect, useRef } from "react";
import { API_BASE } from "../../config";
import { ensureFreshFcmToken } from "../../lib/fcm-token";

export default function AgentRunner({
  scenarioText,
  driverToken,
  passengerToken,
  customerToken, // optional
  onSummary,
  onKpi,
  onEvent,
}) {
  const esRef = useRef(null);

  useEffect(() => {
    if (!scenarioText) return;

    (async () => {
      try {
        await ensureFreshFcmToken(); // safe no-op if unsupported
      } catch (err) {
        onEvent?.({
          type: "error",
          error: `FCM token error: ${String(err?.message || err)}`,
        });
      }
    })();

    if (esRef.current) {
      try {
        esRef.current.close();
      } catch {}
      esRef.current = null;
    }

    const url = new URL(`${API_BASE}/api/agent/run`);
    url.searchParams.set("scenario", scenarioText);
    if (driverToken) url.searchParams.set("driver_token", driverToken);
    if (passengerToken) url.searchParams.set("passenger_token", passengerToken);
    if (customerToken) url.searchParams.set("customer_token", customerToken);

    const es = new EventSource(url.toString(), { withCredentials: false });
    esRef.current = es;

    es.onmessage = (e) => {
      const raw = (e?.data ?? "").trim();
      if (!raw) return;
      if (raw === "[DONE]") {
        onEvent?.({ type: "done" });
        return;
      }
      let obj = null;
      try {
        obj = JSON.parse(raw);
      } catch {
        onEvent?.({ type: "text", text: raw });
        return;
      }
      onEvent?.(obj);

      const summary =
        obj?.summary ??
        obj?.data?.summary ??
        (obj?.type === "summary" ? obj?.data ?? "" : undefined);
      if (summary != null) onSummary?.(summary);

      const k = obj?.kpis ?? obj?.data?.kpis ?? obj;
      const obs = obj?.observation ?? obj?.data?.observation;

      const etaObs = asNum(obs?.duration_traffic_min ?? obs?.duration_min);
      const distObsKm = asNum(obs?.distance_km);
      const alertsCount = asNum(k?.alerts ?? k?.alert_count);

      const etaMin = asNum(k?.etaMin ?? k?.eta_minutes ?? k?.eta ?? etaObs);
      const distanceKm = asNum(
        k?.distanceKm ?? k?.distance_km ?? k?.distance ?? distObsKm
      );

      if (etaMin != null || distanceKm != null || alertsCount != null) {
        onKpi?.({ etaMin, distanceKm, alerts: alertsCount });
      }
    };

    es.onerror = (err) => {
      onEvent?.({ type: "error", error: String(err?.message || err) });
      try {
        es.close();
      } catch {}
    };

    return () => {
      try {
        es.close();
      } catch {}
      esRef.current = null;
    };
  }, [scenarioText, driverToken, passengerToken, customerToken]);

  return null;
}

function asNum(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}
