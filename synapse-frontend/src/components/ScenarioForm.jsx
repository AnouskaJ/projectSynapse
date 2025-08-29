import React, { useMemo, useState } from "react";

export default function ScenarioForm({ defaultScenario = "", defaultOriginPlace = "", defaultDestPlace = "", onRun }) {
  const [scenario, setScenario] = useState(defaultScenario);
  const [originPlace, setOriginPlace] = useState(defaultOriginPlace);
  const [destPlace, setDestPlace] = useState(defaultDestPlace);
  const [origin, setOrigin] = useState(""); // "lat,lon" optional
  const [dest, setDest] = useState("");     // "lat,lon" optional

  const canRun = useMemo(() => scenario.trim().length > 0, [scenario]);

  const submit = (e) => {
    e.preventDefault();
    if (!canRun) return;
    onRun?.({
      scenario: scenario.trim(),
      origin_place: originPlace.trim() || undefined,
      dest_place: destPlace.trim() || undefined,
      origin: origin.trim() || undefined,
      dest: dest.trim() || undefined
    });
  };

  return (
    <form onSubmit={submit} className="card space-y-4">
      <div>
        <label className="block text-sm text-gray-300 mb-1">Scenario</label>
        <textarea
          className="w-full rounded-xl bg-black/30 border border-grab-edge px-3 py-2 min-h-[96px]"
          placeholder="Describe the disruption scenario…"
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
        />
      </div>

      <div className="grid md:grid-cols-2 gap-3">
        <div>
          <label className="block text-sm text-gray-300 mb-1">Origin place (optional)</label>
          <input
            className="w-full rounded-xl bg-black/30 border border-grab-edge px-3 py-2"
            placeholder="e.g., Marina Bay Sands"
            value={originPlace}
            onChange={(e) => setOriginPlace(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">Destination place (optional)</label>
          <input
            className="w-full rounded-xl bg-black/30 border border-grab-edge px-3 py-2"
            placeholder="e.g., Changi Airport"
            value={destPlace}
            onChange={(e) => setDestPlace(e.target.value)}
          />
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-3">
        <div>
          <label className="block text-sm text-gray-300 mb-1">Origin coordinates (optional)</label>
          <input
            className="w-full rounded-xl bg-black/30 border border-grab-edge px-3 py-2"
            placeholder="lat,lon (overrides origin place)"
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">Destination coordinates (optional)</label>
          <input
            className="w-full rounded-xl bg-black/30 border border-grab-edge px-3 py-2"
            placeholder="lat,lon (overrides dest place)"
            value={dest}
            onChange={(e) => setDest(e.target.value)}
          />
        </div>
      </div>

      <div className="flex gap-2">
        <button type="submit" className="btn btn-primary" disabled={!canRun}>Run</button>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => { setScenario(defaultScenario || ""); setOriginPlace(defaultOriginPlace || ""); setDestPlace(defaultDestPlace || ""); setOrigin(""); setDest(""); }}
        >
          Reset
        </button>
      </div>
    </form>
  );
}
