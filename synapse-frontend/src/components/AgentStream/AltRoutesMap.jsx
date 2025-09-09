import React, { useEffect, useRef, useState } from "react";
import { MAPS_BROWSER_KEY } from "../../config";

/** Load Maps JS API once (include geometry for polyline decoding) */
const loadGoogleMaps = (() => {
  let promise;
  return () => {
    if (promise) return promise;
    if (window.google?.maps) {
      promise = Promise.resolve(window.google.maps);
      return promise;
    }
    promise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = `https://maps.googleapis.com/maps/api/js?key=${MAPS_BROWSER_KEY}&v=weekly&libraries=geometry`;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve(window.google.maps);
      script.onerror = () => reject(new Error("Failed to load Maps JS API"));
      document.head.appendChild(script);
    });
    return promise;
  };
})();

/** Fallback polyline decoder (if geometry.encoding.decodePath is unavailable) */
const decodePolylineFallback = (str) => {
  if (!str || typeof str !== "string") return [];
  let i = 0,
    lat = 0,
    lng = 0,
    pts = [];
  while (i < str.length) {
    let b,
      shift = 0,
      res = 0;
    do {
      b = str.charCodeAt(i++) - 63;
      res |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20);
    const dlat = res & 1 ? ~(res >> 1) : res >> 1;
    lat += dlat;
    shift = 0;
    res = 0;
    do {
      b = str.charCodeAt(i++) - 63;
      res |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20);
    const dlng = res & 1 ? ~(res >> 1) : res >> 1;
    lng += dlng;
    pts.push({ lat: lat / 1e5, lng: lng / 1e5 });
  }
  return pts;
};

export default function AltRoutesMap({
  routes,
  bounds,
  selectedRoute: selectedRouteProp = 0,
  onChangeSelected, // <- NEW: notify parent when user clicks a polyline
  onConfirm, // <- NEW: parent can get “Use this route” click
}) {
  const divRef = useRef(null);
  const mapRef = useRef(null);
  const overlaysRef = useRef([]);
  const [selectedRoute, setSelectedRoute] = useState(selectedRouteProp);

  // keep internal state in sync if parent changes selectedRouteProp
  useEffect(() => setSelectedRoute(selectedRouteProp), [selectedRouteProp]);

  const getTrafficColor = (trafficMin, normalMin) => {
    const diff = (trafficMin ?? normalMin ?? 0) - (normalMin ?? 0);
    if (diff > 10) return "#d9534f";
    if (diff > 0) return "#f0ad4e";
    return "#5cb85c";
  };

  const clearOverlays = () => {
    overlaysRef.current.forEach((o) => o?.setMap?.(null));
    overlaysRef.current = [];
  };

  /** Build a path array [{lat,lng}, ...] from various shapes */
  const buildPath = (route, gmaps) => {
    if (!route) return [];
    const encoded =
      route.polyline ||
      route.encodedPolyline ||
      route.points ||
      route?.overview_polyline?.points ||
      route.overview_polyline ||
      null;

    if (encoded && typeof encoded === "string") {
      const decoded =
        gmaps?.geometry?.encoding?.decodePath?.(encoded) ||
        decodePolylineFallback(encoded);

      if (Array.isArray(decoded) && decoded.length) {
        if (decoded[0]?.lat && typeof decoded[0].lat === "function") {
          return decoded.map((ll) => ({ lat: ll.lat(), lng: ll.lng() }));
        }
        return decoded;
      }
    }

    if (Array.isArray(route.path) && route.path.length) {
      if (Array.isArray(route.path[0])) {
        return route.path.map(([lat, lng]) => ({ lat, lng }));
      }
      return route.path;
    }

    return [];
  };

  const renderRoutes = (gmaps) => {
    if (!mapRef.current || !Array.isArray(routes) || routes.length === 0)
      return;
    clearOverlays();

    routes.forEach((route, i) => {
      const path = buildPath(route, gmaps);
      if (!path.length) return;

      const isSelected = i === selectedRoute;

      const polyline = new gmaps.Polyline({
        path,
        strokeOpacity: isSelected ? 1.0 : 0.6,
        strokeWeight: isSelected ? 8 : 6,
        strokeColor: isSelected
          ? getTrafficColor(route.trafficMin, route.durationMin)
          : "#333333",
        map: mapRef.current,
        zIndex: isSelected ? 2 : 1,
      });

      overlaysRef.current.push(polyline);
      polyline.addListener("click", () => {
        setSelectedRoute(i);
        onChangeSelected?.(i);
      });
    });

    if (
      bounds &&
      Number.isFinite(bounds.south) &&
      Number.isFinite(bounds.west) &&
      Number.isFinite(bounds.north) &&
      Number.isFinite(bounds.east)
    ) {
      const mapBounds = new gmaps.LatLngBounds(
        new gmaps.LatLng(bounds.south, bounds.west),
        new gmaps.LatLng(bounds.north, bounds.east)
      );
      mapRef.current.fitBounds(mapBounds, 32);
    } else if (
      routes[selectedRoute] &&
      buildPath(routes[selectedRoute], gmaps).length > 0
    ) {
      const routePath = buildPath(routes[selectedRoute], gmaps);
      const mapBounds = new gmaps.LatLngBounds();
      routePath.forEach((point) =>
        mapBounds.extend(new gmaps.LatLng(point.lat, point.lng))
      );
      mapRef.current.fitBounds(mapBounds, 32);
    }
  };

  useEffect(() => {
    let cancel = false;

    const initMap = async () => {
      try {
        const gmaps = await loadGoogleMaps();
        if (cancel || !divRef.current) return;

        await gmaps.importLibrary?.("maps");
        await gmaps.importLibrary?.("geometry").catch(() => null);

        if (!mapRef.current) {
          mapRef.current = new gmaps.Map(divRef.current, {
            center: { lat: 12.9716, lng: 77.5946 },
            zoom: 12,
            gestureHandling: "greedy",
          });
        }

        renderRoutes(gmaps);
      } catch (err) {
        console.error("Error initializing Google Maps:", err);
      }
    };

    initMap();
    return () => {
      cancel = true;
    };
  }, [routes, bounds, selectedRoute]);

  const selected = routes?.[selectedRoute] || {};
  const title = selected.summary ?? "DEFAULT_ROUTE";
  const tMin = selected.trafficMin ?? selected.durationMin ?? "—";
  const baseMin = selected.durationMin ?? "—";

  return (
    <div>
      <div className="altmap-wrap">
        <div
          ref={divRef}
          className="altmap-canvas h-96 w-full rounded-2xl border border-[var(--grab-edge)] bg-black/20"
        />
        <div className="altmap-overlay">
          <div className="altmap-box">
            <div className="altmap-box-title">{title}</div>
            <div className="altmap-box-meta">
              {tMin} min{" "}
              <span className="muted">({baseMin} min without traffic)</span>
            </div>
            {onConfirm && (
              <button
                className="btn btn-primary sm"
                onClick={() => onConfirm(selectedRoute)}
                title="Use this route"
              >
                Use this route
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="mt-4">
        <h3 className="text-gray-400 text-sm mb-2">Alternative Routes</h3>
        <div className="flex flex-col gap-2">
          {(routes || []).map((route, i) => (
            <div
              key={i}
              onClick={() => {
                setSelectedRoute(i);
                onChangeSelected?.(i);
              }}
              className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                i === selectedRoute
                  ? "bg-white/10 border-blue-400"
                  : "bg-black/20 border-gray-700"
              }`}
            >
              <div className="font-semibold text-white">
                {route.summary ?? "DEFAULT_ROUTE"}
              </div>
              <div className="text-sm text-gray-300">
                {route.trafficMin ?? route.durationMin ?? "—"} min{" "}
                <span className="text-gray-500">
                  ({route.durationMin ?? "—"} min without traffic)
                </span>
              </div>
            </div>
          ))}
          {!routes?.length && (
            <div className="text-sm text-gray-500">
              No alternate routes available.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
