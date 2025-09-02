import React, { useEffect, useRef } from "react";
import { MAPS_BROWSER_KEY } from "../../config";

/* ------------------------------------------------------------------ */
/*  Google Maps JS loader – runs ONCE per page                        */
/* ------------------------------------------------------------------ */
let mapsLoaderPromise = null;

function loadMaps(apiKey) {
  /* Already loaded? */
  if (window.google?.maps) return Promise.resolve();

  /* Loader already in-flight? Re-use it. */
  if (mapsLoaderPromise) return mapsLoaderPromise;

  /* New load */
  mapsLoaderPromise = new Promise((resolve, reject) => {
    const cb = "__init_google_maps";              // stable global cb

    /* Avoid redefining the callback if another component added it */
    if (!window[cb]) window[cb] = () => resolve();

    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&callback=${cb}`;
    s.async = true;
    s.defer = true;
    s.onerror = reject;
    document.head.appendChild(s);
  });

  return mapsLoaderPromise;
}

/* ------------------------------------------------------------------ */
/*  MerchantMap component                                             */
/* ------------------------------------------------------------------ */
export default function MerchantMap({ center, merchants }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!MAPS_BROWSER_KEY || !merchants?.length) return;

    let map; // keep local ref for cleanup

    loadMaps(MAPS_BROWSER_KEY)
      .then(() => {
        if (!ref.current) return; // component unmounted

        map = new window.google.maps.Map(ref.current, {
          zoom: 15,
          center,
          disableDefaultUI: true,
          clickableIcons: false,
        });

        const bounds = new window.google.maps.LatLngBounds();

        merchants.forEach((m) => {
          const pos = { lat: m.lat, lng: m.lng ?? m.lon };

          /* Use the new AdvancedMarkerElement when available */
          if (window.google.maps.marker?.AdvancedMarkerElement) {
            new window.google.maps.marker.AdvancedMarkerElement({
              map,
              position: pos,
              title: m.name,
            });
          } else {
            /* Fallback to classic Marker (deprecated but still works) */
            new window.google.maps.Marker({ map, position: pos, title: m.name });
          }

          bounds.extend(pos);
        });

        /* Fit map to show all pins (or just centre on the single pin) */
        if (!bounds.isEmpty()) {
          if (merchants.length === 1) {
            map.setCenter(bounds.getCenter());
            map.setZoom(16);
          } else {
            map.fitBounds(bounds, 64);
          }
        }
      })
      .catch(console.error);

    /* optional cleanup */
    return () => (map = null);
  }, [center, merchants]);

  return (
    <div
      ref={ref}
      style={{
        height: 400,
        width: "100%",
        borderRadius: 12,
        overflow: "hidden",
      }}
    />
  );
}
