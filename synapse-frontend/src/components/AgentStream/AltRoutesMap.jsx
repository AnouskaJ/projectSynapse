/* src/components/AgentStream/AltRoutesMap.jsx */
import React, { useEffect, useRef, useState } from "react";
import { MAPS_BROWSER_KEY } from "../../config";

/* --- loader ---------------------------------------------------------- */
const loadMaps = (() => {
  let p;
  return () => {
    if (p) return p;
    p = new Promise((res, rej) => {
      if (window.google?.maps) return res(window.google.maps);
      const s = document.createElement("script");
      s.src = `https://maps.googleapis.com/maps/api/js?key=${MAPS_BROWSER_KEY}&libraries=geometry`;
      s.async = true;
      s.defer = true;
      s.onload = () => res(window.google.maps);
      s.onerror = () => rej(new Error("Maps JS failed"));
      document.head.appendChild(s);
    });
    return p;
  };
})();

/* --- tiny polyline decoder fallback ---------------------------------- */
const decode = (str) => {
  let i = 0, lat = 0, lng = 0, pts = [];
  while (i < str.length) {
    let b, shift = 0, res = 0;
    do { b = str.charCodeAt(i++) - 63; res |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
    lat += res & 1 ? ~(res >> 1) : res >> 1;
    shift = 0; res = 0;
    do { b = str.charCodeAt(i++) - 63; res |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
    lng += res & 1 ? ~(res >> 1) : res >> 1;
    pts.push({ lat: lat / 1e5, lng: lng / 1e5 });
  }
  return pts;
};

/* --------------------------------------------------------------------- */
export default function AltRoutesMap({ routes = [], showAlternatives = true }) {
  const host   = useRef(null);   // <div> container
  const gmap   = useRef(null);   // google.maps.Map
  const lines  = useRef([]);     // drawn polylines / markers
  const [sel, setSel] = useState(0);

  /* helper: clear previous overlays */
  const clear = () => { lines.current.forEach(l => l.setMap(null)); lines.current = []; };

  const colour = (i, active) =>
    active ? "#4285F4" : "#BDBDBD"; // Google blue vs light-grey

  /* draw whenever routes / sel change */
  useEffect(() => {
    let stop = false;
    (async () => {
      const gm = await loadMaps();
      if (stop || !host.current) return;

      if (!gmap.current) {
        gmap.current = new gm.Map(host.current, {
          center: { lat: 12.9716, lng: 77.5946 },
          zoom: 12,
          gestureHandling: "greedy",
        });
      }

      clear();
      if (!routes.length) return;

      const bounds = new gm.LatLngBounds();

      routes.forEach((r, i) => {
        if (!showAlternatives && i > 0) return;
        if (!r.polyline) return;

        const path = gm.geometry?.encoding?.decodePath(r.polyline) || decode(r.polyline);
        path.forEach(p => bounds.extend(p));

        lines.current.push(
          new gm.Polyline({
            map: gmap.current,
            path,
            strokeColor: colour(i, i === sel),
            strokeWeight: i === sel ? 6 : 4,
            strokeOpacity: i === sel ? 1 : 0.7,
            zIndex: i === sel ? 2 : 1,
          })
        );
      });

      gmap.current.fitBounds(bounds, 64);
    })();
    return () => { stop = true; };
  }, [routes, sel, showAlternatives]);

  /* ------------------------------------------------------------------- */
  return (
    <div>
      <div ref={host} className="h-96 w-full rounded-2xl border border-[var(--grab-edge)] bg-black/20" />

      {showAlternatives && (
        <div className="mt-4 space-y-2">
          {routes.map((r, i) => (
            <button
              key={i}
              onClick={() => setSel(i)}
              className={`w-full p-3 text-left rounded-md border
                ${i === sel ? "bg-[#4285F4]/10 border-[#4285F4]" : "bg-black/30 border-gray-700"}`}
            >
              <div className="font-semibold text-white">{r.summary}</div>
              <div className="text-sm text-gray-300">
                {r.trafficMin} min{" "}
                <span className="text-gray-500">({r.durationMin} min no traffic)</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
