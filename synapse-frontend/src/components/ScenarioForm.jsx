"use client"

import { useMemo, useState } from "react"

export default function ScenarioForm({ defaultScenario = "", onRun }) {
  const [scenario, setScenario] = useState(defaultScenario)
  const canRun = useMemo(() => scenario.trim().length > 0, [scenario])

  const count = scenario.length
  const helperId = "scenario-helper"

  const submit = (e) => {
    e.preventDefault()
    if (!canRun) return
    onRun?.(scenario.trim())
  }

  return (
    <form onSubmit={submit} className="card space-y-4 p-4">
      <div>
        <label htmlFor="scenario" className="block text-sm text-gray-300 mb-1">
          Scenario
        </label>
        <textarea
          id="scenario"
          aria-describedby={helperId}
          className="w-full rounded-xl bg-black/30 border border-[var(--grab-edge)] px-3 py-2 min-h-[130px] focus:outline-none focus:ring-2 focus:ring-[var(--grab-green)]"
          placeholder="Describe the disruption scenario…"
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
          style={{ lineHeight: 1.5 }}
        />
        <div id={helperId} className="k mt-1">
          {count} characters
        </div>
      </div>
      <div className="flex gap-2 flex-wrap">
        <button type="submit" className="btn btn-primary" disabled={!canRun}>
          Run
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => setScenario(defaultScenario || "")}
          title="Reset to default scenario"
        >
          Reset
        </button>
      </div>
    </form>
  )
}
