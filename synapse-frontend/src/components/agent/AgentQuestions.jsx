export default function AgentQuestions({ routes = [], onPick }) {
  if (!Array.isArray(routes) || !routes.length) return null;

  return (
    <div className="gt-card p-3 mt-3 gt-choice-card">
      <div className="mb-2 text-sm font-semibold">Agent Questions</div>
      <div className="space-y-2">
        {routes.map((r, idx) => {
          const title = r.name || r.id || `Route ${idx + 1}`;
          const bits = [
            r.etaMin != null ? `${r.etaMin} min` : null,
            r.etaNoTraffic != null ? `${r.etaNoTraffic} min (no traffic)` : null,
            r.distanceKm != null ? `${r.distanceKm} km` : null,
          ]
            .filter(Boolean)
            .join(" · ");

          return (
            <button key={idx} className="gt-choice-btn" onClick={() => onPick?.(idx, r)}>
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium">{title}</div>
                <div className="text-xs text-[var(--grab-muted)]">{bits || "—"}</div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
