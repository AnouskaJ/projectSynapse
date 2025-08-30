// src/utils/api.js
import { getIdToken } from "../lib/auth";

export const API_BASE =
  import.meta.env.VITE_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:5000";

/**
 * Build the /api/agent/run SSE URL with query params.
 * Accepts { scenario, origin, dest, origin_place, dest_place, driver_token, passenger_token, customer_token }
 * Always appends ?token=<firebase-id-token> if available.
 */
export async function buildRunUrl(params) {
  const q = new URLSearchParams();

  if (params.scenario) q.set("scenario", params.scenario);
  if (params.origin) q.set("origin", params.origin);            // "lat,lon"
  if (params.dest) q.set("dest", params.dest);                  // "lat,lon"
  if (params.origin_place) q.set("origin_place", params.origin_place);
  if (params.dest_place) q.set("dest_place", params.dest_place);
  if (params.driver_token) q.set("driver_token", params.driver_token);
  if (params.passenger_token) q.set("passenger_token", params.passenger_token);
  if (params.customer_token) q.set("customer_token", params.customer_token);

  // 🔑 append Firebase ID token for backend auth
  const token = await getIdToken();
  if (token) q.set("token", token);

  return `${API_BASE}/api/agent/run?${q.toString()}`;
}

/**
 * Simple helper for GET JSON endpoints.
 * Automatically adds Authorization: Bearer <idToken> if logged in.
 */
export async function getJson(path) {
  const token = await getIdToken();
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}
