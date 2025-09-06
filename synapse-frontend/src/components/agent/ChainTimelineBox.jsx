import ChainTimeline from "./ChainTimeline.jsx";

export default function ChainTimelineBox({
  events,
  title = "Agent Timeline",
  className = "",
  fullHeight = false,
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
        <div className="gt-dim text-xs">{events?.length ?? 0} items</div>
      </div>
      <ChainTimeline events={events} />
    </div>
  );
}
