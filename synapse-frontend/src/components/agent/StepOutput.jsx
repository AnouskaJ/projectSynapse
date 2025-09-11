import React from "react";
import PrettyObject from "../AgentStream/PrettyObject.jsx";
import Pill from "../AgentStream/Pill.jsx";
import UnifiedMap from "../ui/UnifiedMap.jsx";

export default function StepOutput({ step }) {
  if (!step) {
    return (
      <div className="gt-card p-4 text-sm text-[var(--grab-muted)] flex items-center justify-center">
        Click a step in the timeline to see its details.
      </div>
    );
  }

  const ok = step.passed;
  const title = step.intent || "Step Details";

  return (
    <div className="gt-card p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-semibold">{title}</div>
        <Pill tone={ok ? "ok" : "err"}>
          {ok ? "passed" : "passed"}
        </Pill>
      </div>
      
      {/* Map rendered first */}
      <div className="mt-3">
        <UnifiedMap event={step} />
      </div>

      <div className="space-y-4">
        <div>
          <h4 className="text-xs uppercase tracking-wider text-[var(--grab-muted)]">Tool Parameters</h4>
          <PrettyObject data={step.params} />
        </div>
        <div>
          <h4 className="text-xs uppercase tracking-wider text-[var(--grab-muted)]">Observation</h4>
          <PrettyObject data={step.observation} />
        </div>
        {step.message && (
          <div>
            <h4 className="text-xs uppercase tracking-wider text-[var(--grab-muted)]">Message</h4>
            <pre className="summary-pre">{step.message}</pre>
          </div>
        )}
      </div>
    </div>
  );
}