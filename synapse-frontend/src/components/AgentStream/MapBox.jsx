/* src/components/AgentStream/MapBox.jsx */
import React, { useEffect, useRef } from "react";
import { decodePolyline, loadGoogleMaps } from "./googleMaps";

/* -----------------------------------------------------------
   Lightweight live-map panel
   ----------------------------------------------------------- */
export default function MapBox({ payload }) {
  const divRef      = useRef(null);   // <div> that hosts the map
  const mapRef      = useRef(null);   // google.maps.Map instance
  const overlaysRef = useRef([]);     // keep polylines / markers to clear

  /* -------- util helpers -------- */
  const clear = () => {
    overlaysRef.current.forEach(o => o.setMap(null));
    overlaysRef.current = [];
  };

  const fit = (gmaps, b) => {
    if (!b || !mapRef.current) return;
    const bounds = new gmaps.LatLngBounds(
      new gmaps.LatLng(b.south, b.west),
      new gmaps.LatLng(b.north, b.east)
    );
    mapRef.current.fitBounds(bounds, 32);
  };

  const poly = (gmaps, enc, opts = {}) =>
    new gmaps.Polyline({
      path: gmaps.geometry?.encoding?.decodePath(enc) || decodePolyline(enc),
      ...opts,
      map: mapRef.current,
    });

  /* -------- render whenever `payload` changes -------- */
  useEffect(() => {
    let cancelled = false;

    (async () => {
      const gmaps = await loadGoogleMaps();
      if (cancelled || !divRef.current) return;

      /* Create the Map once */
      if (!mapRef.current) {
        mapRef.current = new gmaps.Map(divRef.current, {
          center: { lat: 12.9716, lng: 77.5946 },
          zoom:   12,
          gestureHandling: "greedy",
        });
      }

      /* Nothing to draw? */
      if (!payload) return;
      clear();

      /* ---- directions (array of routes) ---- */
      if (payload.kind === "directions") {
        payload.routes?.forEach((r, i) => {
          if (!r.polyline) return;
          overlaysRef.current.push(
            poly(gmaps, r.polyline, {
              strokeOpacity: i ? 0.6 : 0.95,
              strokeWeight : i ? 4   : 6,
            })
          );
        });
        fit(gmaps, payload.bounds);
      }

      /* ---- plain markers ---- */
      if (payload.kind === "markers") {
        payload.markers?.forEach(({ position, title }) => {
          const Adv = gmaps.marker?.AdvancedMarkerElement; // new-style
          overlaysRef.current.push(
            Adv
              ? new Adv({ map: mapRef.current, position, title })
              : new gmaps.Marker({ map: mapRef.current, position, title })
          );
        });
        fit(gmaps, payload.bounds);
      }

      /* ---- compare_routes ---- */
      if (payload.kind === "compare_routes") {
        const { baseline, candidate } = payload;
        if (baseline?.polyline)
          overlaysRef.current.push(
            poly(gmaps, baseline.polyline, { strokeOpacity: 0.4, strokeWeight: 5 })
          );
        if (candidate?.polyline)
          overlaysRef.current.push(
            poly(gmaps, candidate.polyline, { strokeWeight: 6 })
          );
        fit(gmaps, payload.bounds);
      }
    })().catch((e) => console.warn("[MapBox]", e));

    return () => { cancelled = true; };
  }, [payload]);

  /* container */
  return (
    <div
      ref={divRef}
      className="h-96 w-full rounded-2xl border border-[var(--grab-edge)] bg-black/20"
    />
  );
}
