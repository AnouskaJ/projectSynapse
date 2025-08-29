export const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:5000";

/**
 * Build the /api/agent/run SSE URL with query params.
 * Accepts { scenario, origin, dest, origin_place, dest_place, driver_token, passenger_token }
 */
export function buildRunUrl(params) {
  const q = new URLSearchParams();
  if (params.scenario) q.set("scenario", params.scenario);
  if (params.origin) q.set("origin", params.origin);            // "lat,lon"
  if (params.dest) q.set("dest", params.dest);                  // "lat,lon"
  if (params.origin_place) q.set("origin_place", params.origin_place);
  if (params.dest_place) q.set("dest_place", params.dest_place);
  if (params.driver_token) q.set("driver_token", params.driver_token);
  if (params.passenger_token) q.set("passenger_token", params.passenger_token);
  return `${API_BASE}/api/agent/run?${q.toString()}`;
}

/** Simple helper for GET JSON endpoints if needed later */
export async function getJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}
