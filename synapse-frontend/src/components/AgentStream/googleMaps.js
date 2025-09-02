/* src/components/AgentStream/googleMaps.js */
import { MAPS_BROWSER_KEY } from "../../config";

/* --- 1.  Promise-memoised loader ------------------------------------ */
let mapsPromise;

export const loadGoogleMaps = () => {
  if (mapsPromise) return mapsPromise;

  mapsPromise = new Promise((resolve, reject) => {
    /* Already on page? */
    if (window.google?.maps?.Map) {
      resolve(window.google.maps);
      return;
    }

    /* Inject <script> exactly once */
    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${MAPS_BROWSER_KEY}&libraries=geometry`;
    s.async = true;
    s.defer = true;

    s.onload = () => {
      if (window.google?.maps?.Map) resolve(window.google.maps);
      else reject(new Error("Google Maps JS loaded but Map ctor missing"));
    };
    s.onerror = () => reject(new Error("Failed to load Google Maps JS"));
    document.head.appendChild(s);
  });

  return mapsPromise;
};

/* --- 2.  Tiny fallback polyline decoder ----------------------------- */
export const decodePolyline = (str) => {
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
