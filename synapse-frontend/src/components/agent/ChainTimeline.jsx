// Internal helpers are scoped to the component so pages don't need them
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
    return x.map((i) => (typeof i === "string" ? i : safeStringify(i))).join("\n");
  if (typeof x === "object") {
    if (typeof x.text === "string") return x.text;
    if (typeof x.message === "string") return x.message;
    return safeStringify(x);
  }
  return String(x);
}

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

export default function ChainTimeline({ events }) {
  if (!events?.length) {
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
                  <KeyVal title="Tool" data={data.tool ? { tool: data.tool } : null} />
                  <KeyVal title="Params" data={ev.params || data.params} />
                  <KeyVal title="Observation" data={ev.observation || data.observation} />
                </div>
              </details>
            )}
          </div>
        );
      })}
    </div>
  );
}
