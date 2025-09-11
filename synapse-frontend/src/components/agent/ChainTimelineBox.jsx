import ChainTimeline from "./ChainTimeline.jsx";

/**
 * Box wrapper for the agent timeline.
 * Now supports an optional "onMaximize" prop that shows a ⤢ button in the header.
 */
export default function ChainTimelineBox({
  events,
  title = "Agent Timeline",
  className = "",
  fullHeight = false,
  onMaximize, // ← new (optional) prop
  onStepClick, // 👈 New prop
  onSummaryClick, // 👈 New prop
}) {
  const rootCls = [
    "gt-card",
    "gt-timeline-card",
    className,
    fullHeight ? "gt-timeline-grow" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rootCls}>
      <div className="flex items-center justify-between p-3">
        <div className="text-sm font-semibold">{title}</div>
        <div className="flex items-center gap-2">
          {onMaximize && (
            <button
              className="btn gt-icon"
              title="Maximize"
              aria-label="Maximize timeline"
              onClick={onMaximize}
            >
              ⤢
            </button>
          )}
          <div className="gt-dim text-xs">{events?.length ?? 0} items</div>
        </div>
      </div>
      {/* 👈 Pass the new props down to the child component */}
      <ChainTimeline events={events} onStepClick={onStepClick} onSummaryClick={onSummaryClick} />
    </div>
  );
}