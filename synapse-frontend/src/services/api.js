// Minimal fetch helpers (JSON + SSE)
export async function getJSON(url, opts = {}) {
  const res = await fetch(url, { credentials: "include", ...opts });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// Subscribe to an SSE endpoint and parse JSON lines.
export function subscribeSSE(url, { onMessage, onError, onOpen }) {
  const es = new EventSource(url, { withCredentials: true });
  if (onOpen) es.onopen = onOpen;
  es.onerror = (e) => { if (onError) onError(e); es.close(); };
  es.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)); } catch { /* ignore */ }
  };
  return () => es.close();
}
